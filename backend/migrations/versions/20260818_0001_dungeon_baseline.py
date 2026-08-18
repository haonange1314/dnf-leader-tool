"""create dungeon definition baseline

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "formula_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formula_versions")),
        sa.UniqueConstraint("code", "version", name=op.f("uq_formula_versions_code")),
    )
    op.create_table(
        "dungeons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dungeons")),
        sa.UniqueConstraint("code", name=op.f("uq_dungeons_code")),
    )
    op.create_table(
        "dungeon_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dungeon_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("default_wave_count", sa.SmallInteger(), nullable=False),
        sa.Column("min_wave_count", sa.SmallInteger(), nullable=False),
        sa.Column("max_wave_count", sa.SmallInteger(), nullable=True),
        sa.Column("formula_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composition_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("special_role_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strength_order_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("optimization_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_slot_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_no > 0", name=op.f("ck_dungeon_versions_positive_version_no")),
        sa.CheckConstraint(
            "default_wave_count > 0", name=op.f("ck_dungeon_versions_positive_default_wave_count")
        ),
        sa.CheckConstraint(
            "min_wave_count > 0", name=op.f("ck_dungeon_versions_positive_min_wave_count")
        ),
        sa.CheckConstraint(
            "max_wave_count IS NULL OR max_wave_count >= min_wave_count",
            name=op.f("ck_dungeon_versions_valid_wave_count_range"),
        ),
        sa.CheckConstraint(
            "default_wave_count >= min_wave_count AND (max_wave_count IS NULL OR default_wave_count <= max_wave_count)",
            name=op.f("ck_dungeon_versions_default_wave_count_in_range"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'RETIRED')",
            name=op.f("ck_dungeon_versions_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["dungeon_id"],
            ["dungeons.id"],
            name=op.f("fk_dungeon_versions_dungeon_id_dungeons"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["formula_version_id"],
            ["formula_versions.id"],
            name=op.f("fk_dungeon_versions_formula_version_id_formula_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dungeon_versions")),
        sa.UniqueConstraint(
            "dungeon_id", "version_no", name=op.f("uq_dungeon_versions_dungeon_id")
        ),
    )
    op.create_index(
        op.f("ix_dungeon_versions_dungeon_id"), "dungeon_versions", ["dungeon_id"], unique=False
    )
    op.create_table(
        "dungeon_team_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dungeon_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_key", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("display_color", sa.String(length=20), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.Column("member_count", sa.SmallInteger(), nullable=False),
        sa.Column("strength_rank", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint(
            "member_count > 0", name=op.f("ck_dungeon_team_templates_positive_member_count")
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_dungeon_team_templates_non_negative_display_order")
        ),
        sa.CheckConstraint(
            "strength_rank IS NULL OR strength_rank > 0",
            name=op.f("ck_dungeon_team_templates_positive_strength_rank"),
        ),
        sa.ForeignKeyConstraint(
            ["dungeon_version_id"],
            ["dungeon_versions.id"],
            name=op.f("fk_dungeon_team_templates_dungeon_version_id_dungeon_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dungeon_team_templates")),
        sa.UniqueConstraint(
            "dungeon_version_id",
            "display_order",
            name="uq_dungeon_team_templates_version_display_order",
        ),
        sa.UniqueConstraint(
            "dungeon_version_id", "team_key", name="uq_dungeon_team_templates_version_team_key"
        ),
    )
    op.create_index(
        op.f("ix_dungeon_team_templates_dungeon_version_id"),
        "dungeon_team_templates",
        ["dungeon_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dungeon_team_templates_dungeon_version_id"), table_name="dungeon_team_templates"
    )
    op.drop_table("dungeon_team_templates")
    op.drop_index(op.f("ix_dungeon_versions_dungeon_id"), table_name="dungeon_versions")
    op.drop_table("dungeon_versions")
    op.drop_table("dungeons")
    op.drop_table("formula_versions")
