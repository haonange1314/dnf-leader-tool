"""enforce one profession per player

Revision ID: 20260828_0010
Revises: 20260821_0009
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0010"
down_revision: str | Sequence[str] | None = "20260821_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def upgrade() -> None:
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text(
                "SELECT id, player_id, profession FROM characters "
                "ORDER BY player_id, created_at, id"
            )
        ).mappings()
    )
    seen: dict[tuple[object, str], object] = {}
    duplicates: list[str] = []
    updates: list[dict[str, object]] = []
    for row in rows:
        profession_key = _normalize_key(str(row["profession"]))
        key = (row["player_id"], profession_key)
        if key in seen:
            duplicates.append(
                f"player={row['player_id']} profession={row['profession']} "
                f"characters={seen[key]},{row['id']}"
            )
        else:
            seen[key] = row["id"]
        updates.append({"character_id": row["id"], "profession_key": profession_key})
    if duplicates:
        details = "; ".join(duplicates[:10])
        raise RuntimeError(
            "同一玩家存在重复职业，无法迁移；请先清理重复角色。" f"{details}"
        )

    connection.execute(sa.text("UPDATE characters SET name_key = id::text"))
    if updates:
        connection.execute(
            sa.text(
                "UPDATE characters SET name_key = :profession_key "
                "WHERE id = :character_id"
            ),
            updates,
        )


def downgrade() -> None:
    op.execute("UPDATE characters SET name_key = id::text")
