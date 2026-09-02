from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("wave_count > 0 AND wave_count <= 50", name="valid_wave_count"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    dungeon_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dungeon_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    formula_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formula_versions.id", ondelete="RESTRICT"), nullable=False
    )
    wave_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    note: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_published_version: Mapped[int | None] = mapped_column(Integer)
    validation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    active_rule_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "schedule_rule_sets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_schedules_active_rule_set_id",
        ),
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    participants: Mapped[list[ScheduleParticipant]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )
    preferences: Mapped[list[SchedulePlayerPreference]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )
    waves: Mapped[list[Wave]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="Wave.wave_no"
    )
    generation_runs: Mapped[list[GenerationRun]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )
    rule_sets: Mapped[list[ScheduleRuleSet]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        foreign_keys="ScheduleRuleSet.schedule_id",
        order_by="ScheduleRuleSet.created_at",
    )
    active_rule_set: Mapped[ScheduleRuleSet | None] = relationship(
        foreign_keys=[active_rule_set_id], post_update=True
    )
    versions: Mapped[list[ScheduleVersion]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleVersion.version_no",
    )
    edit_operations: Mapped[list[ScheduleEditOperation]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class ScheduleRuleSet(Base):
    __tablename__ = "schedule_rule_sets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PARSED','CONFIRMED','STALE','SUPERSEDED','FAILED')",
            name="valid_status",
        ),
        Index("ix_schedule_rule_sets_schedule_id_created_at", "schedule_id", "created_at"),
        Index(
            "uq_schedule_rule_sets_confirmed_schedule",
            "schedule_id",
            unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    parsed_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    resolved_references: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedule: Mapped[Schedule] = relationship(
        back_populates="rule_sets", foreign_keys=[schedule_id]
    )


class EditLock(Base):
    __tablename__ = "edit_locks"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lock_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ScheduleParticipant(Base):
    __tablename__ = "schedule_participants"
    __table_args__ = (UniqueConstraint("schedule_id", "character_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("characters.id", ondelete="RESTRICT"), nullable=False
    )
    player_id_snapshot: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    player_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    character_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    profession_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    role_type_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    damage_score_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    buffer_score_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    is_treasure_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_fixed_lead_team_buffer_snapshot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_group_hunt_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unassigned_reason: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    schedule: Mapped[Schedule] = relationship(back_populates="participants")


class SchedulePlayerPreference(Base):
    __tablename__ = "schedule_player_preferences"
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="RESTRICT"), primary_key=True
    )
    allowed_waves: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    max_wave_count: Mapped[int | None] = mapped_column(SmallInteger)
    prefer_early: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prefer_contiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule: Mapped[Schedule] = relationship(back_populates="preferences")


class Wave(Base):
    __tablename__ = "waves"
    __table_args__ = (
        UniqueConstraint("schedule_id", "wave_no"),
        CheckConstraint("wave_no > 0", name="positive_wave_no"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wave_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    damage_total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    buffer_total: Mapped[Decimal] = mapped_column(Numeric(10, 1), nullable=False, default=0)
    schedule: Mapped[Schedule] = relationship(back_populates="waves")
    teams: Mapped[list[Team]] = relationship(
        back_populates="wave", cascade="all, delete-orphan", order_by="Team.display_order_snapshot"
    )
    special_assignments: Mapped[list[WaveSpecialAssignment]] = relationship(
        back_populates="wave",
        cascade="all, delete-orphan",
        order_by="WaveSpecialAssignment.rule_code",
    )


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("wave_id", "team_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wave_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waves.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_key: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    display_color_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    display_order_snapshot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    member_count_snapshot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    strength_rank_snapshot: Mapped[int | None] = mapped_column(SmallInteger)
    damage_total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    buffer_total: Mapped[Decimal] = mapped_column(Numeric(10, 1), nullable=False, default=0)
    composition_code: Mapped[str] = mapped_column(String(40), nullable=False, default="INCOMPLETE")
    wave: Mapped[Wave] = relationship(back_populates="teams")
    slots: Mapped[list[TeamSlot]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="TeamSlot.slot_no"
    )


class TeamSlot(Base):
    __tablename__ = "team_slots"
    __table_args__ = (
        UniqueConstraint("team_id", "slot_no"),
        CheckConstraint("slot_no > 0", name="positive_slot_no"),
        Index("ix_team_slots_schedule_id_wave_id", "schedule_id", "wave_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wave_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waves.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_participants.id", ondelete="SET NULL"), unique=True
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    team: Mapped[Team] = relationship(back_populates="slots")


class WaveSpecialAssignment(Base):
    __tablename__ = "wave_special_assignments"
    __table_args__ = (
        UniqueConstraint(
            "wave_id",
            "rule_code",
            "participant_id",
            name="uq_wave_special_assignments_wave_rule_participant",
        ),
        Index("ix_wave_special_assignments_schedule_id_wave_id", "schedule_id", "wave_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False
    )
    wave_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waves.id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(40), nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedule_participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_team_key_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    wave: Mapped[Wave] = relationship(back_populates="special_assignments")


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED','STALE')",
            name="valid_status",
        ),
        Index("ix_generation_runs_schedule_id_created_at", "schedule_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False
    )
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result_revision: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solver_version: Mapped[str] = mapped_column(String(40), nullable=False)
    formula_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formula_versions.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_rule_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_rule_sets.id", ondelete="SET NULL"), index=True
    )
    rule_compiler_version: Mapped[str | None] = mapped_column(String(40))
    effective_rules: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    rule_evaluation: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    objective_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedule: Mapped[Schedule] = relationship(back_populates="generation_runs")


class ScheduleEditOperation(Base):
    __tablename__ = "schedule_edit_operations"
    __table_args__ = (
        Index("ix_schedule_edit_operations_schedule_id_created_at", "schedule_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False
    )
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    schedule: Mapped[Schedule] = relationship(back_populates="edit_operations")


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id", "version_no", name="uq_schedule_versions_schedule_version"
        ),
        Index("ix_schedule_versions_schedule_id_published_at", "schedule_id", "published_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formula_versions.id", ondelete="RESTRICT"), nullable=False
    )
    published_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    schedule: Mapped[Schedule] = relationship(back_populates="versions")
    share_links: Mapped[list[ShareLink]] = relationship(
        back_populates="schedule_version", cascade="all, delete-orphan"
    )


class ShareLink(Base):
    __tablename__ = "share_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schedule_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    schedule_version: Mapped[ScheduleVersion] = relationship(back_populates="share_links")
