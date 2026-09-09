"""replace roster traits with versioned buffer conversion

Revision ID: 20260909_0017
Revises: 20260904_0016
Create Date: 2026-09-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260909_0017"
down_revision: str | None = "20260904_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This product reset intentionally removes historical business records while preserving RBAC.
    op.execute("DROP TRIGGER trg_schedule_versions_immutable ON schedule_versions")
    op.execute("DELETE FROM share_links")
    op.execute("DELETE FROM schedule_versions")
    op.execute("DELETE FROM schedules")
    op.execute(
        "CREATE TRIGGER trg_schedule_versions_immutable BEFORE UPDATE OR DELETE "
        "ON schedule_versions FOR EACH ROW EXECUTE FUNCTION reject_schedule_version_mutation()"
    )
    op.execute("DELETE FROM import_batches")
    op.execute("DELETE FROM audit_logs")
    op.execute(
        "UPDATE dungeon_versions SET status = 'RETIRED' "
        "WHERE status = 'PUBLISHED' AND dungeon_id IN "
        "(SELECT id FROM dungeons WHERE code = 'BUILTIN_RAID_12')"
    )

    op.create_table(
        "buffer_conversion_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.execute(
        """
        INSERT INTO permissions (id, code, name, module, description)
        VALUES
          (gen_random_uuid(), 'BUFFER_CONVERSION_READ', '查看奶量换算', '系统管理', '查看奶量换算规则和历史版本'),
          (gen_random_uuid(), 'BUFFER_CONVERSION_WRITE', '维护奶量换算', '系统管理', '创建新的奶量换算配置版本')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT roles.id, permissions.id
        FROM roles CROSS JOIN permissions
        WHERE roles.code = 'OWNER'
          AND permissions.code IN ('BUFFER_CONVERSION_READ', 'BUFFER_CONVERSION_WRITE')
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO buffer_conversion_versions (id, version, rules, is_active)
        VALUES (
          gen_random_uuid(), 1,
          '[{"profession":"奶爸","multiplier":"0.997"},'
          ' {"profession":"奶枪","multiplier":"0.995"},'
          ' {"profession":"奶妈","multiplier":"1.000"},'
          ' {"profession":"奶萝","multiplier":"1.040"},'
          ' {"profession":"缪斯","multiplier":"1.002"}]'::jsonb,
          true
        )
        """
    )
    op.add_column(
        "schedules",
        sa.Column("buffer_conversion_version_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_schedules_buffer_conversion_version_id",
        "schedules",
        "buffer_conversion_versions",
        ["buffer_conversion_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("schedule_participants_character_id_fkey", "schedule_participants", type_="foreignkey")
    op.alter_column("schedule_participants", "character_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key(
        "schedule_participants_character_id_fkey",
        "schedule_participants",
        "characters",
        ["character_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "schedule_player_preferences_player_id_fkey",
        "schedule_player_preferences",
        type_="foreignkey",
    )

    op.drop_column("schedule_participants", "is_group_hunt_snapshot")
    op.drop_column("schedule_participants", "is_fixed_lead_team_buffer_snapshot")
    op.drop_column("schedule_participants", "is_treasure_snapshot")
    op.alter_column(
        "teams",
        "buffer_total",
        existing_type=sa.Numeric(10, 1),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "waves",
        "buffer_total",
        existing_type=sa.Numeric(10, 1),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.drop_constraint("group_hunt_requires_damage", "characters", type_="check")
    op.drop_constraint("fixed_lead_team_requires_buffer", "characters", type_="check")
    op.drop_constraint("treasure_requires_damage", "characters", type_="check")
    op.drop_column("characters", "default_raid_participant")
    op.drop_column("characters", "is_group_hunt")
    op.drop_column("characters", "is_fixed_lead_team_buffer")
    op.drop_column("characters", "is_treasure_damage")


def downgrade() -> None:
    op.create_foreign_key(
        "schedule_player_preferences_player_id_fkey",
        "schedule_player_preferences",
        "players",
        ["player_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "waves",
        "buffer_total",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Numeric(10, 1),
        existing_nullable=False,
    )
    op.alter_column(
        "teams",
        "buffer_total",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Numeric(10, 1),
        existing_nullable=False,
    )
    op.add_column("characters", sa.Column("is_treasure_damage", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("characters", sa.Column("is_fixed_lead_team_buffer", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("characters", sa.Column("is_group_hunt", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("characters", sa.Column("default_raid_participant", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.create_check_constraint("treasure_requires_damage", "characters", "role_type = 'DAMAGE' OR is_treasure_damage = false")
    op.create_check_constraint("fixed_lead_team_requires_buffer", "characters", "role_type = 'BUFFER' OR is_fixed_lead_team_buffer = false")
    op.create_check_constraint("group_hunt_requires_damage", "characters", "role_type = 'DAMAGE' OR is_group_hunt = false")
    op.add_column("schedule_participants", sa.Column("is_treasure_snapshot", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("schedule_participants", sa.Column("is_fixed_lead_team_buffer_snapshot", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("schedule_participants", sa.Column("is_group_hunt_snapshot", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.drop_constraint("schedule_participants_character_id_fkey", "schedule_participants", type_="foreignkey")
    op.alter_column("schedule_participants", "character_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.create_foreign_key("schedule_participants_character_id_fkey", "schedule_participants", "characters", ["character_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("fk_schedules_buffer_conversion_version_id", "schedules", type_="foreignkey")
    op.drop_column("schedules", "buffer_conversion_version_id")
    op.drop_table("buffer_conversion_versions")
    op.execute("DELETE FROM permissions WHERE code IN ('BUFFER_CONVERSION_READ', 'BUFFER_CONVERSION_WRITE')")
