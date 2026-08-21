"""index stale login rate-limit cleanup

Revision ID: 20260821_0009
Revises: 20260821_0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0009"
down_revision: str | Sequence[str] | None = "20260821_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_login_rate_limits_updated_at",
        "login_rate_limits",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_rate_limits_updated_at", table_name="login_rate_limits")
