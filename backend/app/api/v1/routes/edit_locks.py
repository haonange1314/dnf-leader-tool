import uuid

from fastapi import APIRouter, Request

from app.api.dependencies import CurrentUser, DbSession, EditorUser
from app.application.schedule_locks import (
    acquire_edit_lock,
    edit_lock_view,
    heartbeat_edit_lock,
    release_edit_lock,
    takeover_edit_lock,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.schedule import Schedule
from app.schemas.edit_lock import EditLockView

router = APIRouter()


def _require_schedule(db: DbSession, schedule_id: uuid.UUID) -> None:
    if db.get(Schedule, schedule_id) is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")


def _token(request: Request) -> str:
    token = request.headers.get(get_settings().edit_lock_header_name)
    if not token:
        raise AppError(423, "EDIT_LOCK_TOKEN_REQUIRED", "请求缺少编辑锁令牌")
    return token


@router.get("/schedules/{schedule_id}/lock", response_model=EditLockView)
def get_lock(schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> EditLockView:
    _require_schedule(db, schedule_id)
    return edit_lock_view(db, schedule_id, current_user.id, get_settings())


@router.post("/schedules/{schedule_id}/lock", response_model=EditLockView)
def acquire_lock(
    schedule_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: EditorUser,
) -> EditLockView:
    _require_schedule(db, schedule_id)
    settings = get_settings()
    grant = acquire_edit_lock(
        db,
        schedule_id,
        current_user.id,
        settings,
        request.headers.get(settings.edit_lock_header_name),
    )
    db.commit()
    return edit_lock_view(db, schedule_id, current_user.id, settings, token=grant.token)


@router.post("/schedules/{schedule_id}/lock/heartbeat", response_model=EditLockView)
def heartbeat_lock(
    schedule_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: EditorUser,
) -> EditLockView:
    settings = get_settings()
    token = _token(request)
    heartbeat_edit_lock(db, schedule_id, current_user.id, token, settings)
    db.commit()
    return edit_lock_view(db, schedule_id, current_user.id, settings, token=token)


@router.delete("/schedules/{schedule_id}/lock", status_code=204)
def release_lock(
    schedule_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: EditorUser,
) -> None:
    release_edit_lock(db, schedule_id, current_user.id, _token(request))
    db.commit()


@router.post("/schedules/{schedule_id}/lock/takeover", response_model=EditLockView)
def takeover_lock(
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: EditorUser,
) -> EditLockView:
    _require_schedule(db, schedule_id)
    settings = get_settings()
    grant = takeover_edit_lock(db, schedule_id, current_user.id, settings)
    db.commit()
    return edit_lock_view(db, schedule_id, current_user.id, settings, token=grant.token)
