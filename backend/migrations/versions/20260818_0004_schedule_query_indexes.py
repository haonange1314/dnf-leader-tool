"""add schedule query indexes

Revision ID: 20260818_0004
Revises: 20260818_0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0004"
down_revision: str | Sequence[str] | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_teams_wave_id", "teams", ["wave_id"])
    op.create_index("ix_team_slots_team_id", "team_slots", ["team_id"])
    op.create_index(
        "ix_team_slots_schedule_id_wave_id", "team_slots", ["schedule_id", "wave_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_team_slots_schedule_id_wave_id", table_name="team_slots")
    op.drop_index("ix_team_slots_team_id", table_name="team_slots")
    op.drop_index("ix_teams_wave_id", table_name="teams")
