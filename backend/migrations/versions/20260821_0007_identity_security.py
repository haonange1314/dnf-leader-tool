"""add identity security and audit baseline

Revision ID: 20260821_0007
Revises: 20260820_0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0007"
down_revision: str | Sequence[str] | None = "20260820_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing sessions predate CSRF binding and must be invalidated once.
    op.execute("DELETE FROM user_sessions")
    op.execute("ALTER TABLE user_sessions ADD COLUMN csrf_token_hash varchar(64) NOT NULL")
    op.execute("""
    CREATE TABLE login_rate_limits (
      key_hash varchar(64) PRIMARY KEY,
      attempt_count integer NOT NULL,
      window_started_at timestamptz NOT NULL,
      blocked_until timestamptz,
      updated_at timestamptz NOT NULL
    );
    CREATE INDEX ix_login_rate_limits_blocked_until ON login_rate_limits(blocked_until);

    CREATE TABLE audit_logs (
      id uuid PRIMARY KEY,
      actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
      action varchar(120) NOT NULL,
      outcome varchar(16) NOT NULL,
      request_id varchar(80) NOT NULL,
      ip_address varchar(64),
      resource_type varchar(80),
      resource_id varchar(120),
      details jsonb NOT NULL,
      created_at timestamptz NOT NULL,
      CONSTRAINT ck_audit_logs_valid_outcome CHECK (outcome IN ('SUCCESS', 'FAILURE'))
    );
    CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs(actor_user_id);
    CREATE INDEX ix_audit_logs_action ON audit_logs(action);
    CREATE INDEX ix_audit_logs_request_id ON audit_logs(request_id);
    CREATE INDEX ix_audit_logs_created_at ON audit_logs(created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE audit_logs")
    op.execute("DROP TABLE login_rate_limits")
    op.execute("ALTER TABLE user_sessions DROP COLUMN csrf_token_hash")
