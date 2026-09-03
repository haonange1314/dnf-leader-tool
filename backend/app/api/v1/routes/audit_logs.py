import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import AuditReader, DbSession
from app.models.identity import AuditLog, User
from app.schemas.auth import AuditLogList, AuditLogView

router = APIRouter()


@router.get("/audit-logs", response_model=AuditLogList)
def list_audit_logs(
    db: DbSession,
    current_user: AuditReader,
    search: str | None = Query(default=None, max_length=120),
    actor_user_id: Annotated[uuid.UUID | None, Query(alias="actorUserId")] = None,
    outcome: str | None = Query(default=None, pattern="^(SUCCESS|FAILURE)$"),
    action: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, alias="resourceType", max_length=80),
    started_at: Annotated[datetime | None, Query(alias="startedAt")] = None,
    ended_at: Annotated[datetime | None, Query(alias="endedAt")] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditLogList:
    del current_user
    filters: list[ColumnElement[bool]] = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            AuditLog.request_id.ilike(term)
            | AuditLog.resource_id.ilike(term)
            | AuditLog.ip_address.ilike(term)
        )
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if outcome:
        filters.append(AuditLog.outcome == outcome)
    if action:
        filters.append(AuditLog.action == action)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if started_at:
        filters.append(AuditLog.created_at >= started_at)
    if ended_at:
        filters.append(AuditLog.created_at <= ended_at)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = db.execute(
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return AuditLogList(
        items=[
            AuditLogView.model_validate(
                {
                    "id": log.id,
                    "actor_user_id": log.actor_user_id,
                    "actor_username": username,
                    "action": log.action,
                    "outcome": log.outcome,
                    "request_id": log.request_id,
                    "ip_address": log.ip_address,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "details": log.details,
                    "created_at": log.created_at,
                }
            )
            for log, username in rows
        ],
        total=total,
    )
