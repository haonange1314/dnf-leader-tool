"""add schedule editor receipts, versions and share links

Revision ID: 20260820_0006
Revises: 20260818_0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260820_0006"
down_revision: str | Sequence[str] | None = "20260818_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE schedules ADD COLUMN last_published_version integer")
    op.execute("""
    CREATE TABLE schedule_edit_operations (
      id uuid PRIMARY KEY,
      schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      input_revision integer NOT NULL,
      result_revision integer NOT NULL,
      response jsonb NOT NULL,
      created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_schedule_edit_operations_schedule_id_created_at
      ON schedule_edit_operations(schedule_id, created_at);

    CREATE TABLE schedule_versions (
      id uuid PRIMARY KEY,
      schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE RESTRICT,
      version_no integer NOT NULL,
      source_revision integer NOT NULL,
      snapshot_schema_version integer NOT NULL,
      snapshot jsonb NOT NULL,
      snapshot_hash varchar(64) NOT NULL,
      formula_version_id uuid NOT NULL REFERENCES formula_versions(id) ON DELETE RESTRICT,
      published_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      published_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_schedule_versions_schedule_version UNIQUE(schedule_id, version_no)
    );
    CREATE INDEX ix_schedule_versions_schedule_id_published_at
      ON schedule_versions(schedule_id, published_at);

    CREATE TABLE share_links (
      id uuid PRIMARY KEY,
      schedule_version_id uuid NOT NULL REFERENCES schedule_versions(id) ON DELETE CASCADE,
      token_hash varchar(64) NOT NULL,
      expires_at timestamptz,
      revoked_at timestamptz,
      created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_share_links_token_hash UNIQUE(token_hash)
    );
    CREATE INDEX ix_share_links_schedule_version_id ON share_links(schedule_version_id);
    """)
    op.execute("""
    CREATE FUNCTION reject_schedule_version_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'schedule_versions are immutable';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_schedule_versions_immutable
      BEFORE UPDATE OR DELETE ON schedule_versions
      FOR EACH ROW EXECUTE FUNCTION reject_schedule_version_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_schedule_versions_immutable ON schedule_versions")
    op.execute("DROP FUNCTION reject_schedule_version_mutation()")
    op.execute("DROP TABLE share_links")
    op.execute("DROP TABLE schedule_versions")
    op.execute("DROP TABLE schedule_edit_operations")
    op.execute("ALTER TABLE schedules DROP COLUMN last_published_version")
