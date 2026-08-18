"""add identity personnel and import staging

Revision ID: 20260818_0002
Revises: 20260818_0001
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0002"
down_revision: str | Sequence[str] | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE formula_versions
        SET config = jsonb_build_object(
            'damageUnit', COALESCE(config->'damage_unit', config->'damageUnit'),
            'damageScale', COALESCE(config->'damage_scale', config->'damageScale'),
            'bufferScale', COALESCE(config->'buffer_scale', config->'bufferScale'),
            'teamDamageMode', COALESCE(config->'team_damage_mode', config->'teamDamageMode'),
            'twoBufferMode', COALESCE(config->'two_buffer_mode', config->'twoBufferMode')
        )
        """
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('OWNER', 'EDITOR', 'VIEWER')", name=op.f("ck_users_valid_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "players",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("display_name_key", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
        sa.UniqueConstraint("display_name_key", name=op.f("uq_players_display_name_key")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"])
    op.create_index(op.f("ix_user_sessions_expires_at"), "user_sessions", ["expires_at"])
    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=120), nullable=False),
        sa.Column("profession", sa.String(length=80), nullable=False),
        sa.Column("role_type", sa.String(length=16), nullable=False),
        sa.Column("damage_score", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("buffer_score", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("is_treasure_damage", sa.Boolean(), nullable=False),
        sa.Column("default_raid_participant", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role_type IN ('DAMAGE', 'BUFFER')", name=op.f("ck_characters_valid_role_type")
        ),
        sa.CheckConstraint(
            "(role_type = 'DAMAGE' AND damage_score IS NOT NULL AND buffer_score IS NULL) OR (role_type = 'BUFFER' AND buffer_score IS NOT NULL AND damage_score IS NULL)",
            name=op.f("ck_characters_score_matches_role_type"),
        ),
        sa.CheckConstraint(
            "role_type = 'DAMAGE' OR is_treasure_damage = false",
            name=op.f("ck_characters_treasure_requires_damage"),
        ),
        sa.CheckConstraint(
            "(damage_score IS NULL OR damage_score >= 0) AND (buffer_score IS NULL OR buffer_score >= 0)",
            name=op.f("ck_characters_non_negative_scores"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_characters_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_characters")),
        sa.UniqueConstraint("player_id", "name_key", name=op.f("uq_characters_player_id")),
    )
    op.create_index(op.f("ix_characters_player_id"), "characters", ["player_id"])
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PREVIEWED', 'COMMITTED')", name=op.f("ck_import_batches_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_import_batches_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_table(
        "import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched_player_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("matched_character_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('CREATE', 'UPDATE', 'IGNORE', 'ERROR')",
            name=op.f("ck_import_rows_valid_action"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_import_rows_batch_id_import_batches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_rows")),
        sa.UniqueConstraint("batch_id", "row_no", name=op.f("uq_import_rows_batch_id")),
    )
    op.execute(
        """
        CREATE FUNCTION guard_dungeon_version_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'published dungeon versions are immutable';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status = 'DRAFT' THEN
                RETURN NEW;
            END IF;
            IF OLD.status = 'PUBLISHED' AND NEW.status = 'RETIRED'
               AND NEW.id IS NOT DISTINCT FROM OLD.id
               AND NEW.dungeon_id IS NOT DISTINCT FROM OLD.dungeon_id
               AND NEW.version_no IS NOT DISTINCT FROM OLD.version_no
               AND NEW.default_wave_count IS NOT DISTINCT FROM OLD.default_wave_count
               AND NEW.min_wave_count IS NOT DISTINCT FROM OLD.min_wave_count
               AND NEW.max_wave_count IS NOT DISTINCT FROM OLD.max_wave_count
               AND NEW.formula_version_id IS NOT DISTINCT FROM OLD.formula_version_id
               AND NEW.composition_rules IS NOT DISTINCT FROM OLD.composition_rules
               AND NEW.special_role_rules IS NOT DISTINCT FROM OLD.special_role_rules
               AND NEW.strength_order_rules IS NOT DISTINCT FROM OLD.strength_order_rules
               AND NEW.optimization_rules IS NOT DISTINCT FROM OLD.optimization_rules
               AND NEW.missing_slot_policy IS NOT DISTINCT FROM OLD.missing_slot_policy
               AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
               AND NEW.published_at IS NOT DISTINCT FROM OLD.published_at THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'published dungeon versions are immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_guard_dungeon_version_mutation
        BEFORE UPDATE OR DELETE ON dungeon_versions
        FOR EACH ROW EXECUTE FUNCTION guard_dungeon_version_mutation();

        CREATE FUNCTION guard_dungeon_team_mutation() RETURNS trigger AS $$
        DECLARE version_status varchar(16);
        DECLARE version_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                version_id := OLD.dungeon_version_id;
            ELSE
                version_id := NEW.dungeon_version_id;
            END IF;
            SELECT status INTO version_status FROM dungeon_versions
            WHERE id = version_id;
            IF version_status <> 'DRAFT' THEN
                RAISE EXCEPTION 'teams of published dungeon versions are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_guard_dungeon_team_mutation
        BEFORE UPDATE OR DELETE ON dungeon_team_templates
        FOR EACH ROW EXECUTE FUNCTION guard_dungeon_team_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_guard_dungeon_team_mutation ON dungeon_team_templates")
    op.execute("DROP FUNCTION guard_dungeon_team_mutation()")
    op.execute("DROP TRIGGER trg_guard_dungeon_version_mutation ON dungeon_versions")
    op.execute("DROP FUNCTION guard_dungeon_version_mutation()")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
    op.drop_index(op.f("ix_characters_player_id"), table_name="characters")
    op.drop_table("characters")
    op.drop_index(op.f("ix_user_sessions_expires_at"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("players")
    op.drop_table("users")
