"""add per-schedule damage balance tolerance

Revision ID: 20260909_0018
Revises: 20260909_0017
Create Date: 2026-09-09 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0018"
down_revision: str | None = "20260909_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column(
            "damage_balance_tolerance_percent",
            sa.SmallInteger(),
            server_default=sa.text("20"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_damage_balance_tolerance_percent",
        "schedules",
        "damage_balance_tolerance_percent >= 0 "
        "AND damage_balance_tolerance_percent <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_damage_balance_tolerance_percent", "schedules", type_="check"
    )
    op.drop_column("schedules", "damage_balance_tolerance_percent")
