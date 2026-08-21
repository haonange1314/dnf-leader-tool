"""add single-editor schedule leases

Revision ID: 20260821_0008
Revises: 20260821_0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0008"
down_revision: str | Sequence[str] | None = "20260821_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE edit_locks (
      schedule_id uuid PRIMARY KEY REFERENCES schedules(id) ON DELETE CASCADE,
      user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      lock_token_hash varchar(64) NOT NULL,
      acquired_at timestamptz NOT NULL,
      heartbeat_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL
    );
    CREATE INDEX ix_edit_locks_user_id ON edit_locks(user_id);
    CREATE INDEX ix_edit_locks_expires_at ON edit_locks(expires_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE edit_locks")
