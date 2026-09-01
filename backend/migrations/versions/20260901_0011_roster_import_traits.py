"""support roster import traits and precise buffer scores

Revision ID: 20260901_0011
Revises: 20260828_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0011"
down_revision: str | Sequence[str] | None = "20260828_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "characters",
        "buffer_score",
        existing_type=sa.Numeric(precision=8, scale=1),
        type_=sa.Numeric(precision=8, scale=2),
        existing_nullable=True,
    )
    op.add_column(
        "characters",
        sa.Column(
            "is_fixed_lead_team_buffer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "is_group_hunt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "fixed_lead_team_requires_buffer",
        "characters",
        "role_type = 'BUFFER' OR is_fixed_lead_team_buffer = false",
    )
    op.create_check_constraint(
        "group_hunt_requires_damage",
        "characters",
        "role_type = 'DAMAGE' OR is_group_hunt = false",
    )

    op.alter_column(
        "schedule_participants",
        "buffer_score_snapshot",
        existing_type=sa.Numeric(precision=8, scale=1),
        type_=sa.Numeric(precision=8, scale=2),
        existing_nullable=True,
    )
    op.add_column(
        "schedule_participants",
        sa.Column(
            "is_fixed_lead_team_buffer_snapshot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "schedule_participants",
        sa.Column(
            "is_group_hunt_snapshot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_participants", "is_group_hunt_snapshot")
    op.drop_column("schedule_participants", "is_fixed_lead_team_buffer_snapshot")
    op.alter_column(
        "schedule_participants",
        "buffer_score_snapshot",
        existing_type=sa.Numeric(precision=8, scale=2),
        type_=sa.Numeric(precision=8, scale=1),
        existing_nullable=True,
    )

    op.drop_constraint("group_hunt_requires_damage", "characters", type_="check")
    op.drop_constraint("fixed_lead_team_requires_buffer", "characters", type_="check")
    op.drop_column("characters", "is_group_hunt")
    op.drop_column("characters", "is_fixed_lead_team_buffer")
    op.alter_column(
        "characters",
        "buffer_score",
        existing_type=sa.Numeric(precision=8, scale=2),
        type_=sa.Numeric(precision=8, scale=1),
        existing_nullable=True,
    )
