from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import create_edit_lock_token, hash_edit_lock_token, utc_now
from app.models.identity import User
from app.models.schedule import EditLock
from app.schemas.edit_lock import EditLockView


@dataclass(frozen=True)
class EditLockGrant:
    row: EditLock
    token: str


def _locked_details(db: Session, row: EditLock) -> dict[str, object]:
    holder = db.get(User, row.user_id)
    expired = row.expires_at <= utc_now()
    return {
        "holderUserId": str(row.user_id),
        "holderUsername": holder.username if holder is not None else None,
        "expiresAt": row.expires_at.isoformat(),
        "canTakeover": expired,
    }


def acquire_edit_lock(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    settings: Settings,
    existing_token: str | None,
) -> EditLockGrant:
    now = utc_now()
    token = create_edit_lock_token()
    inserted_id = db.execute(
        insert(EditLock)
        .values(
            schedule_id=schedule_id,
            user_id=user_id,
            lock_token_hash=hash_edit_lock_token(token),
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=settings.edit_lock_lease_seconds),
        )
        .on_conflict_do_nothing(index_elements=[EditLock.schedule_id])
        .returning(EditLock.schedule_id)
    ).scalar_one_or_none()
    if inserted_id is not None:
        row = db.get(EditLock, schedule_id)
        if row is None:  # pragma: no cover - defensive after INSERT RETURNING
            raise RuntimeError("edit lock insert was not visible")
        return EditLockGrant(row=row, token=token)

    row = db.scalar(select(EditLock).where(EditLock.schedule_id == schedule_id).with_for_update())
    if row is None:  # pragma: no cover - concurrent delete retries on the next request
        raise AppError(409, "EDIT_LOCK_RETRY", "编辑锁状态刚刚变化，请重试")
    if (
        row.expires_at > now
        and row.user_id == user_id
        and existing_token
        and secrets.compare_digest(hash_edit_lock_token(existing_token), row.lock_token_hash)
    ):
        row.heartbeat_at = now
        row.expires_at = now + timedelta(seconds=settings.edit_lock_lease_seconds)
        return EditLockGrant(row=row, token=existing_token)
    raise AppError(
        423,
        "EDIT_LOCKED",
        "排表正在被其他编辑会话使用",
        details=_locked_details(db, row),
    )


def takeover_edit_lock(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    settings: Settings,
) -> EditLockGrant:
    now = utc_now()
    row = db.scalar(select(EditLock).where(EditLock.schedule_id == schedule_id).with_for_update())
    if row is None:
        return acquire_edit_lock(db, schedule_id, user_id, settings, None)
    if row.expires_at > now:
        raise AppError(
            423,
            "EDIT_LOCK_ACTIVE",
            "编辑锁尚未过期，不能接管",
            details=_locked_details(db, row),
        )
    token = create_edit_lock_token()
    row.user_id = user_id
    row.lock_token_hash = hash_edit_lock_token(token)
    row.acquired_at = now
    row.heartbeat_at = now
    row.expires_at = now + timedelta(seconds=settings.edit_lock_lease_seconds)
    return EditLockGrant(row=row, token=token)


def heartbeat_edit_lock(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    token: str,
    settings: Settings,
) -> EditLock:
    row = _require_edit_lock_row(db, schedule_id, user_id, token, for_update=True)
    now = utc_now()
    row.heartbeat_at = now
    row.expires_at = now + timedelta(seconds=settings.edit_lock_lease_seconds)
    return row


def release_edit_lock(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    token: str,
) -> None:
    row = _require_edit_lock_row(db, schedule_id, user_id, token, for_update=True)
    db.delete(row)


def require_edit_lock(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    token: str,
) -> EditLock:
    return _require_edit_lock_row(db, schedule_id, user_id, token, for_update=True)


def _require_edit_lock_row(
    db: Session,
    schedule_id: uuid.UUID,
    user_id: uuid.UUID,
    token: str,
    *,
    for_update: bool,
) -> EditLock:
    statement = select(EditLock).where(EditLock.schedule_id == schedule_id)
    if for_update:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise AppError(423, "EDIT_LOCK_REQUIRED", "请先获取此排表的编辑锁")
    if row.expires_at <= utc_now():
        raise AppError(423, "EDIT_LOCK_EXPIRED", "编辑锁已过期，请重新接管")
    if row.user_id != user_id or not secrets.compare_digest(
        hash_edit_lock_token(token), row.lock_token_hash
    ):
        raise AppError(423, "EDIT_LOCK_INVALID", "当前编辑锁不属于此会话")
    return row


def edit_lock_view(
    db: Session,
    schedule_id: uuid.UUID,
    current_user_id: uuid.UUID,
    settings: Settings,
    *,
    token: str | None = None,
) -> EditLockView:
    row = db.get(EditLock, schedule_id)
    if row is None:
        return EditLockView(
            schedule_id=schedule_id,
            held=False,
            can_takeover=True,
            heartbeat_interval_seconds=settings.effective_edit_lock_heartbeat_seconds,
            token=token,
        )
    holder = db.get(User, row.user_id)
    held = row.expires_at > utc_now()
    return EditLockView(
        schedule_id=schedule_id,
        held=held,
        holder_user_id=row.user_id,
        holder_username=holder.username if holder is not None else None,
        owned_by_current_user=held and row.user_id == current_user_id and token is not None,
        can_takeover=not held,
        acquired_at=row.acquired_at,
        heartbeat_at=row.heartbeat_at,
        expires_at=row.expires_at,
        heartbeat_interval_seconds=settings.effective_edit_lock_heartbeat_seconds,
        token=token,
    )
