"""add configurable RBAC roles and permissions

Revision ID: 20260903_0014
Revises: 20260902_0013
Create Date: 2026-09-03
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0014"
down_revision: str | Sequence[str] | None = "20260902_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_IDS = {
    "OWNER": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    "EDITOR": uuid.UUID("00000000-0000-0000-0000-000000000002"),
    "VIEWER": uuid.UUID("00000000-0000-0000-0000-000000000003"),
}

PERMISSIONS = (
    ("10000000-0000-0000-0000-000000000001", "DUNGEON_READ", "查看副本", "副本管理", "查看副本及版本规则"),
    ("10000000-0000-0000-0000-000000000002", "DUNGEON_WRITE", "维护副本", "副本管理", "创建、编辑和发布副本版本"),
    ("10000000-0000-0000-0000-000000000003", "ROSTER_READ", "查看人员", "人员管理", "查看玩家和角色资料"),
    ("10000000-0000-0000-0000-000000000004", "ROSTER_WRITE", "维护人员", "人员管理", "新增、编辑、排序和停用人员"),
    ("10000000-0000-0000-0000-000000000005", "ROSTER_IMPORT", "导入人员", "人员管理", "预览、确认人员导入并下载错误明细"),
    ("10000000-0000-0000-0000-000000000006", "SCHEDULE_READ", "查看排表", "排表管理", "查看排表、版本及生成记录"),
    ("10000000-0000-0000-0000-000000000007", "SCHEDULE_WRITE", "编辑排表", "排表管理", "创建、复制和人工编辑排表"),
    ("10000000-0000-0000-0000-000000000008", "SCHEDULE_GENERATE", "智能排表", "排表管理", "执行自动排表和自然语言规则操作"),
    ("10000000-0000-0000-0000-000000000009", "SCHEDULE_PUBLISH", "发布排表", "排表管理", "发布、恢复和归档排表"),
    ("10000000-0000-0000-0000-000000000010", "SCHEDULE_EXPORT", "导出排表", "排表管理", "下载排表图片、Excel 和文本"),
    ("10000000-0000-0000-0000-000000000011", "SHARE_MANAGE", "管理分享", "排表管理", "创建、查看和撤销分享链接"),
    ("10000000-0000-0000-0000-000000000012", "USER_READ", "查看用户", "系统管理", "查看用户账号和会话摘要"),
    ("10000000-0000-0000-0000-000000000013", "USER_WRITE", "管理用户", "系统管理", "创建、编辑、停用用户并撤销会话"),
    ("10000000-0000-0000-0000-000000000014", "ROLE_READ", "查看角色权限", "系统管理", "查看角色和权限矩阵"),
    ("10000000-0000-0000-0000-000000000015", "ROLE_WRITE", "管理角色权限", "系统管理", "创建角色并调整权限"),
    ("10000000-0000-0000-0000-000000000016", "AUDIT_READ", "查看操作日志", "系统管理", "检索和查看操作审计记录"),
)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("code", name=op.f("uq_roles_code")),
    )
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )
    op.create_index(op.f("ix_permissions_module"), "permissions", ["module"])
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_role_permissions_role_id_roles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], name=op.f("fk_role_permissions_permission_id_permissions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )

    roles_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        roles_table,
        [
            {"id": ROLE_IDS["OWNER"], "code": "OWNER", "name": "系统所有者", "description": "拥有全部权限且不可停用", "is_system": True, "is_active": True},
            {"id": ROLE_IDS["EDITOR"], "code": "EDITOR", "name": "业务编辑者", "description": "维护业务数据、智能排表和发布分享", "is_system": True, "is_active": True},
            {"id": ROLE_IDS["VIEWER"], "code": "VIEWER", "name": "只读查看者", "description": "查看并导出现有业务数据", "is_system": True, "is_active": True},
        ],
    )
    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("module", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "id": uuid.UUID(row[0]),
                "code": row[1],
                "name": row[2],
                "module": row[3],
                "description": row[4],
            }
            for row in PERMISSIONS
        ],
    )

    editor_excluded = {"USER_READ", "USER_WRITE", "ROLE_READ", "ROLE_WRITE", "AUDIT_READ"}
    viewer_codes = {"DUNGEON_READ", "ROSTER_READ", "SCHEDULE_READ", "SCHEDULE_EXPORT"}
    permission_id_by_code = {row[1]: uuid.UUID(row[0]) for row in PERMISSIONS}
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    assignments: list[dict[str, uuid.UUID]] = []
    for code, permission_id in permission_id_by_code.items():
        assignments.append({"role_id": ROLE_IDS["OWNER"], "permission_id": permission_id})
        if code not in editor_excluded:
            assignments.append({"role_id": ROLE_IDS["EDITOR"], "permission_id": permission_id})
        if code in viewer_codes:
            assignments.append({"role_id": ROLE_IDS["VIEWER"], "permission_id": permission_id})
    op.bulk_insert(role_permissions_table, assignments)

    op.add_column("users", sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        "UPDATE users SET role_id = CASE role "
        f"WHEN 'OWNER' THEN '{ROLE_IDS['OWNER']}'::uuid "
        f"WHEN 'EDITOR' THEN '{ROLE_IDS['EDITOR']}'::uuid "
        f"ELSE '{ROLE_IDS['VIEWER']}'::uuid END"
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key(op.f("fk_users_role_id_roles"), "users", "roles", ["role_id"], ["id"], ondelete="RESTRICT")
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"])
    op.drop_constraint(op.f("ck_users_valid_role"), "users", type_="check")
    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=True))
    op.execute(
        "UPDATE users SET role = CASE roles.code "
        "WHEN 'OWNER' THEN 'OWNER' WHEN 'EDITOR' THEN 'EDITOR' ELSE 'VIEWER' END "
        "FROM roles WHERE users.role_id = roles.id"
    )
    op.alter_column("users", "role", nullable=False)
    op.create_check_constraint("ck_users_valid_role", "users", "role IN ('OWNER', 'EDITOR', 'VIEWER')")
    op.drop_index(op.f("ix_users_role_id"), table_name="users")
    op.drop_constraint(op.f("fk_users_role_id_roles"), "users", type_="foreignkey")
    op.drop_column("users", "role_id")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_module"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
