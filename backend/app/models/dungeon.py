from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class FormulaVersion(Base):
    __tablename__ = "formula_versions"
    __table_args__ = (UniqueConstraint("code", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Dungeon(TimestampMixin, Base):
    __tablename__ = "dungeons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    versions: Mapped[list[DungeonVersion]] = relationship(
        back_populates="dungeon", cascade="all, delete-orphan"
    )


class DungeonVersion(Base):
    __tablename__ = "dungeon_versions"
    __table_args__ = (
        UniqueConstraint("dungeon_id", "version_no"),
        CheckConstraint("version_no > 0", name="positive_version_no"),
        CheckConstraint("default_wave_count > 0", name="positive_default_wave_count"),
        CheckConstraint("min_wave_count > 0", name="positive_min_wave_count"),
        CheckConstraint(
            "max_wave_count IS NULL OR max_wave_count >= min_wave_count",
            name="valid_wave_count_range",
        ),
        CheckConstraint(
            "default_wave_count >= min_wave_count AND "
            "(max_wave_count IS NULL OR default_wave_count <= max_wave_count)",
            name="default_wave_count_in_range",
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'RETIRED')", name="valid_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dungeon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dungeons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    default_wave_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    min_wave_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_wave_count: Mapped[int | None] = mapped_column(SmallInteger)
    formula_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("formula_versions.id", ondelete="RESTRICT"), nullable=False
    )
    composition_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    special_role_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    strength_order_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    optimization_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing_slot_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dungeon: Mapped[Dungeon] = relationship(back_populates="versions")
    formula_version: Mapped[FormulaVersion] = relationship()
    teams: Mapped[list[DungeonTeamTemplate]] = relationship(
        back_populates="dungeon_version",
        cascade="all, delete-orphan",
        order_by="DungeonTeamTemplate.display_order",
    )


class DungeonTeamTemplate(Base):
    __tablename__ = "dungeon_team_templates"
    __table_args__ = (
        UniqueConstraint(
            "dungeon_version_id", "team_key", name="uq_dungeon_team_templates_version_team_key"
        ),
        UniqueConstraint(
            "dungeon_version_id",
            "display_order",
            name="uq_dungeon_team_templates_version_display_order",
        ),
        CheckConstraint("member_count > 0", name="positive_member_count"),
        CheckConstraint("display_order >= 0", name="non_negative_display_order"),
        CheckConstraint(
            "strength_rank IS NULL OR strength_rank > 0", name="positive_strength_rank"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dungeon_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dungeon_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_key: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    display_color: Mapped[str] = mapped_column(String(20), nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    member_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    strength_rank: Mapped[int | None] = mapped_column(SmallInteger)

    dungeon_version: Mapped[DungeonVersion] = relationship(back_populates="teams")
