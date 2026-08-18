"""add generation runs and special assignments

Revision ID: 20260818_0005
Revises: 20260818_0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0005"
down_revision: str | Sequence[str] | None = "20260818_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE wave_special_assignments (
      id uuid PRIMARY KEY,
      schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      wave_id uuid NOT NULL REFERENCES waves(id) ON DELETE CASCADE,
      rule_code varchar(40) NOT NULL,
      participant_id uuid NOT NULL REFERENCES schedule_participants(id) ON DELETE CASCADE,
      target_team_key_snapshot varchar(40) NOT NULL,
      CONSTRAINT uq_wave_special_assignments_wave_rule_participant
        UNIQUE(wave_id, rule_code, participant_id)
    );
    CREATE INDEX ix_wave_special_assignments_schedule_id_wave_id
      ON wave_special_assignments(schedule_id, wave_id);

    CREATE TABLE generation_runs (
      id uuid PRIMARY KEY,
      schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      input_revision integer NOT NULL,
      result_revision integer,
      status varchar(16) NOT NULL,
      input_hash varchar(64) NOT NULL,
      solver_version varchar(40) NOT NULL,
      formula_version_id uuid NOT NULL REFERENCES formula_versions(id) ON DELETE RESTRICT,
      random_seed integer NOT NULL,
      time_limit_seconds integer NOT NULL,
      duration_ms integer,
      objective_summary jsonb,
      diagnostics jsonb,
      created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz,
      CONSTRAINT ck_generation_runs_valid_status
        CHECK(status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED','STALE'))
    );
    CREATE INDEX ix_generation_runs_schedule_id_created_at
      ON generation_runs(schedule_id, created_at);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE generation_runs, wave_special_assignments")
