from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
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
    validation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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
    buffer_score_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    is_treasure_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
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
