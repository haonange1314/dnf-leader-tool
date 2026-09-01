"""persist player and character display order

Revision ID: 20260901_0012
Revises: 20260901_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0012"
down_revision: str | Sequence[str] | None = "20260901_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "characters",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (ORDER BY display_name_key, id) - 1 AS sort_order
            FROM players
        )
        UPDATE players
        SET sort_order = ranked.sort_order
        FROM ranked
        WHERE players.id = ranked.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY player_id ORDER BY created_at, id
                ) - 1 AS sort_order
            FROM characters
        )
        UPDATE characters
        SET sort_order = ranked.sort_order
        FROM ranked
        WHERE characters.id = ranked.id
        """
    )


def downgrade() -> None:
    op.drop_column("characters", "sort_order")
    op.drop_column("players", "sort_order")
