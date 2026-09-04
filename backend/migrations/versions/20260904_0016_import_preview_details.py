"""persist roster import preview details and align participation defaults

Revision ID: 20260904_0016
Revises: 20260903_0015
Create Date: 2026-09-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0016"
down_revision: str | None = "20260903_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_batches",
        sa.Column(
            "change_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column(
        "characters",
        "default_raid_participant",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "characters",
        "default_raid_participant",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )
    op.drop_column("import_batches", "change_details")
