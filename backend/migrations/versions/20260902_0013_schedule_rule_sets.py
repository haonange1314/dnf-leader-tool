"""add confirmed natural-language schedule rule sets

Revision ID: 20260902_0013
Revises: 20260901_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0013"
down_revision: str | Sequence[str] | None = "20260901_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "natural_language_rate_limits",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_natural_language_rate_limits_updated_at",
        "natural_language_rate_limits",
        ["updated_at"],
    )
    op.create_table(
        "schedule_rule_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model_provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("provider_response_id", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("parsed_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "resolved_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PARSED','CONFIRMED','STALE','SUPERSEDED','FAILED')",
            name="valid_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_rule_sets_schedule_id_created_at",
        "schedule_rule_sets",
        ["schedule_id", "created_at"],
    )
    op.create_index(
        "uq_schedule_rule_sets_confirmed_schedule",
        "schedule_rule_sets",
        ["schedule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )
    op.add_column("schedules", sa.Column("active_rule_set_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_schedules_active_rule_set_id", "schedules", ["active_rule_set_id"]
    )
    op.create_foreign_key(
        "fk_schedules_active_rule_set_id",
        "schedules",
        "schedule_rule_sets",
        ["active_rule_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "generation_runs", sa.Column("schedule_rule_set_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "generation_runs", sa.Column("rule_compiler_version", sa.String(40), nullable=True)
    )
    op.add_column(
        "generation_runs",
        sa.Column("effective_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "generation_runs",
        sa.Column("rule_evaluation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_generation_runs_schedule_rule_set_id",
        "generation_runs",
        ["schedule_rule_set_id"],
    )
    op.create_foreign_key(
        "fk_generation_runs_schedule_rule_set_id",
        "generation_runs",
        "schedule_rule_sets",
        ["schedule_rule_set_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_generation_runs_schedule_rule_set_id", "generation_runs", type_="foreignkey"
    )
    op.drop_index("ix_generation_runs_schedule_rule_set_id", table_name="generation_runs")
    op.drop_column("generation_runs", "rule_evaluation")
    op.drop_column("generation_runs", "effective_rules")
    op.drop_column("generation_runs", "rule_compiler_version")
    op.drop_column("generation_runs", "schedule_rule_set_id")
    op.drop_constraint("fk_schedules_active_rule_set_id", "schedules", type_="foreignkey")
    op.drop_index("ix_schedules_active_rule_set_id", table_name="schedules")
    op.drop_column("schedules", "active_rule_set_id")
    op.drop_index(
        "uq_schedule_rule_sets_confirmed_schedule", table_name="schedule_rule_sets"
    )
    op.drop_index(
        "ix_schedule_rule_sets_schedule_id_created_at", table_name="schedule_rule_sets"
    )
    op.drop_table("schedule_rule_sets")
    op.drop_index(
        "ix_natural_language_rate_limits_updated_at",
        table_name="natural_language_rate_limits",
    )
    op.drop_table("natural_language_rate_limits")
