from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.models.identity import AuditLog, LoginRateLimit


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


@dataclass(frozen=True)
class LoginLimitBucket:
    key_hash: str
    scope: str
    attempt_limit: int


def _login_limit_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def login_limit_buckets(
    username: str, ip_address: str | None, settings: Settings
) -> tuple[LoginLimitBucket, ...]:
    source = ip_address or "unknown"
    return (
        LoginLimitBucket(
            key_hash=_login_limit_hash(f"account-source|{username}|{source}"),
            scope="ACCOUNT_SOURCE",
            attempt_limit=settings.login_rate_limit_attempts,
        ),
        LoginLimitBucket(
            key_hash=_login_limit_hash(f"source|{source}"),
            scope="SOURCE",
            attempt_limit=settings.login_rate_limit_source_attempts,
        ),
    )


def _lock_login_limit_key(db: Session, key_hash: str) -> None:
    lock_key = int(key_hash[:16], 16)
    if lock_key >= 2**63:
        lock_key -= 2**64
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def _lock_login_limit_buckets(db: Session, buckets: tuple[LoginLimitBucket, ...]) -> None:
    # Deterministic advisory locks serialize first INSERTs without deadlocking overlapping sources.
    for key_hash in sorted(bucket.key_hash for bucket in buckets):
        _lock_login_limit_key(db, key_hash)


def prune_login_rate_limits(db: Session, settings: Settings) -> None:
    now = utc_now()
    retention_seconds = max(
        settings.login_rate_limit_window_seconds,
        settings.login_rate_limit_lock_seconds,
    ) * 2
    cutoff = now - timedelta(seconds=retention_seconds)
    db.execute(
        delete(LoginRateLimit).where(
            LoginRateLimit.updated_at < cutoff,
            (LoginRateLimit.blocked_until.is_(None)) | (LoginRateLimit.blocked_until < now),
        )
    )


def check_login_rate_limits(
    db: Session, buckets: tuple[LoginLimitBucket, ...], settings: Settings
) -> None:
    prune_login_rate_limits(db, settings)
    _lock_login_limit_buckets(db, buckets)
    now = utc_now()
    rows = list(
        db.scalars(
            select(LoginRateLimit)
            .where(LoginRateLimit.key_hash.in_(bucket.key_hash for bucket in buckets))
            .with_for_update()
        )
    )
    blocked = [
        row for row in rows if row.blocked_until is not None and row.blocked_until > now
    ]
    if not blocked:
        return
    retry_after = max(
        1,
        max(int((row.blocked_until - now).total_seconds()) for row in blocked if row.blocked_until),
    )
    blocked_keys = {row.key_hash for row in blocked}
    raise AppError(
        429,
        "LOGIN_RATE_LIMITED",
        "登录尝试过多，请稍后再试",
        details={
            "retryAfterSeconds": retry_after,
            "scopes": [bucket.scope for bucket in buckets if bucket.key_hash in blocked_keys],
        },
    )


def record_login_failure(
    db: Session, buckets: tuple[LoginLimitBucket, ...], settings: Settings
) -> dict[str, int]:
    _lock_login_limit_buckets(db, buckets)
    now = utc_now()
    rows = {
        row.key_hash: row
        for row in db.scalars(
            select(LoginRateLimit)
            .where(LoginRateLimit.key_hash.in_(bucket.key_hash for bucket in buckets))
            .with_for_update()
        )
    }
    attempts: dict[str, int] = {}
    window = timedelta(seconds=settings.login_rate_limit_window_seconds)
    for bucket in buckets:
        limit = rows.get(bucket.key_hash)
        if limit is None:
            limit = LoginRateLimit(
                key_hash=bucket.key_hash,
                attempt_count=1,
                window_started_at=now,
                updated_at=now,
            )
            db.add(limit)
        elif now - limit.window_started_at >= window:
            limit.attempt_count = 1
            limit.window_started_at = now
            limit.blocked_until = None
            limit.updated_at = now
        else:
            limit.attempt_count += 1
            limit.updated_at = now
        if limit.attempt_count >= bucket.attempt_limit:
            limit.blocked_until = now + timedelta(seconds=settings.login_rate_limit_lock_seconds)
        attempts[bucket.scope] = limit.attempt_count
    return attempts


def clear_login_failures(db: Session, buckets: tuple[LoginLimitBucket, ...]) -> None:
    db.execute(
        delete(LoginRateLimit).where(
            LoginRateLimit.key_hash.in_(bucket.key_hash for bucket in buckets)
        )
    )


def add_audit_log(
    db: Session,
    *,
    action: str,
    outcome: str,
    request_id: str,
    ip_address: str | None,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        request_id=request_id,
        ip_address=ip_address,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        created_at=utc_now(),
    )
    db.add(row)
    return row
