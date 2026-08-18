"""add schedule foundation

Revision ID: 20260818_0003
Revises: 20260818_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0003"
down_revision: str | Sequence[str] | None = "20260818_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE schedules (
      id uuid PRIMARY KEY, name varchar(160) NOT NULL,
      dungeon_version_id uuid NOT NULL REFERENCES dungeon_versions(id) ON DELETE RESTRICT,
      formula_version_id uuid NOT NULL REFERENCES formula_versions(id) ON DELETE RESTRICT,
      wave_count smallint NOT NULL, status varchar(16) NOT NULL,
      note text, revision integer NOT NULL, validation_summary jsonb,
      created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      updated_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_schedules_valid_wave_count CHECK (wave_count > 0 AND wave_count <= 50),
      CONSTRAINT ck_schedules_valid_status CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
      CONSTRAINT ck_schedules_positive_revision CHECK (revision > 0)
    );
    CREATE INDEX ix_schedules_dungeon_version_id ON schedules(dungeon_version_id);
    CREATE TABLE schedule_participants (
      id uuid PRIMARY KEY, schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      character_id uuid NOT NULL REFERENCES characters(id) ON DELETE RESTRICT,
      player_id_snapshot uuid NOT NULL, player_name_snapshot varchar(120) NOT NULL,
      character_name_snapshot varchar(120) NOT NULL, profession_snapshot varchar(80) NOT NULL,
      role_type_snapshot varchar(16) NOT NULL, damage_score_snapshot numeric(14,2),
      buffer_score_snapshot numeric(8,1), is_treasure_snapshot boolean NOT NULL,
      is_selected boolean NOT NULL, is_locked boolean NOT NULL, unassigned_reason jsonb,
      CONSTRAINT uq_schedule_participants_schedule_id UNIQUE(schedule_id, character_id)
    );
    CREATE INDEX ix_schedule_participants_schedule_id ON schedule_participants(schedule_id);
    CREATE TABLE schedule_player_preferences (
      schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      player_id uuid NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
      allowed_waves smallint[], max_wave_count smallint,
      prefer_early boolean NOT NULL, prefer_contiguous boolean NOT NULL,
      PRIMARY KEY(schedule_id, player_id)
    );
    CREATE TABLE waves (
      id uuid PRIMARY KEY, schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      wave_no smallint NOT NULL, is_locked boolean NOT NULL,
      damage_total numeric(16,2) NOT NULL, buffer_total numeric(10,1) NOT NULL,
      CONSTRAINT uq_waves_schedule_id UNIQUE(schedule_id, wave_no),
      CONSTRAINT ck_waves_positive_wave_no CHECK(wave_no > 0)
    );
    CREATE INDEX ix_waves_schedule_id ON waves(schedule_id);
    CREATE TABLE teams (
      id uuid PRIMARY KEY, schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      wave_id uuid NOT NULL REFERENCES waves(id) ON DELETE CASCADE, team_key varchar(40) NOT NULL,
      display_name_snapshot varchar(80) NOT NULL, display_color_snapshot varchar(20) NOT NULL,
      display_order_snapshot smallint NOT NULL, member_count_snapshot smallint NOT NULL,
      strength_rank_snapshot smallint, damage_total numeric(16,2) NOT NULL,
      buffer_total numeric(10,1) NOT NULL, composition_code varchar(40) NOT NULL,
      CONSTRAINT uq_teams_wave_id UNIQUE(wave_id, team_key)
    );
    CREATE INDEX ix_teams_schedule_id ON teams(schedule_id);
    CREATE TABLE team_slots (
      id uuid PRIMARY KEY, schedule_id uuid NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
      wave_id uuid NOT NULL REFERENCES waves(id) ON DELETE CASCADE,
      team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
      slot_no smallint NOT NULL,
      participant_id uuid REFERENCES schedule_participants(id) ON DELETE SET NULL,
      is_locked boolean NOT NULL,
      CONSTRAINT uq_team_slots_team_id UNIQUE(team_id, slot_no),
      CONSTRAINT uq_team_slots_participant_id UNIQUE(participant_id),
      CONSTRAINT ck_team_slots_positive_slot_no CHECK(slot_no > 0)
    );
    CREATE INDEX ix_team_slots_schedule_id ON team_slots(schedule_id);
    """)


def downgrade() -> None:
    op.execute(
        "DROP TABLE team_slots, teams, waves, schedule_player_preferences, schedule_participants, schedules"
    )
