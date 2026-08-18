from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Player(TimestampMixin, Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    characters: Mapped[list[Character]] = relationship(
        back_populates="player", cascade="all, delete-orphan", order_by="Character.created_at"
    )


class Character(TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("player_id", "name_key"),
        CheckConstraint("role_type IN ('DAMAGE', 'BUFFER')", name="valid_role_type"),
        CheckConstraint(
            "(role_type = 'DAMAGE' AND damage_score IS NOT NULL AND buffer_score IS NULL) OR "
            "(role_type = 'BUFFER' AND buffer_score IS NOT NULL AND damage_score IS NULL)",
            name="score_matches_role_type",
        ),
        CheckConstraint(
            "role_type = 'DAMAGE' OR is_treasure_damage = false",
            name="treasure_requires_damage",
        ),
        CheckConstraint(
            "(damage_score IS NULL OR damage_score >= 0) AND "
            "(buffer_score IS NULL OR buffer_score >= 0)",
            name="non_negative_scores",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(120), nullable=False)
    profession: Mapped[str] = mapped_column(String(80), nullable=False)
    role_type: Mapped[str] = mapped_column(String(16), nullable=False)
    damage_score: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    buffer_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    is_treasure_damage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_raid_participant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    player: Mapped[Player] = relationship(back_populates="characters")
