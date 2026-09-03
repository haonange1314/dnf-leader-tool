"""add permanent schedule deletion permission

Revision ID: 20260903_0015
Revises: 20260903_0014
Create Date: 2026-09-03
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0015"
down_revision: str | Sequence[str] | None = "20260903_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PERMISSION_ID = uuid.UUID("10000000-0000-0000-0000-000000000017")


def upgrade() -> None:
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
                "id": PERMISSION_ID,
                "code": "SCHEDULE_DELETE",
                "name": "永久删除排表",
                "module": "排表管理",
                "description": "永久删除从未发布的草稿排表",
            }
        ],
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    op.bulk_insert(
        role_permissions_table,
        [{"role_id": OWNER_ROLE_ID, "permission_id": PERMISSION_ID}],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id").bindparams(
            permission_id=PERMISSION_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE id = :permission_id").bindparams(
            permission_id=PERMISSION_ID
        )
    )
