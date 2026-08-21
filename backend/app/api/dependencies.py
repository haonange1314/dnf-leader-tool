import secrets
import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.schedule_locks import require_edit_lock
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_csrf_token, hash_session_token, utc_now
from app.db.session import get_db
from app.models.identity import User, UserSession

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    request: Request,
) -> User:
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise AppError(401, "AUTH_REQUIRED", "请先登录")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(session_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
    )
    if session is None:
        raise AppError(401, "SESSION_INVALID", "登录状态已失效，请重新登录")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AppError(403, "USER_INACTIVE", "账号已停用")
    request.state.current_user_id = user.id
    request.state.current_user_role = user.role
    request.state.current_session_id = session.id
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
        csrf_header = request.headers.get(settings.csrf_header_name)
        if (
            not csrf_cookie
            or not csrf_header
            or not secrets.compare_digest(csrf_cookie, csrf_header)
            or not secrets.compare_digest(hash_csrf_token(csrf_header), session.csrf_token_hash)
        ):
            raise AppError(403, "CSRF_INVALID", "请求安全令牌无效，请刷新页面后重试")
    session.last_seen_at = utc_now()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_editor(current_user: CurrentUser) -> User:
    if current_user.role not in {"OWNER", "EDITOR"}:
        raise AppError(403, "PERMISSION_DENIED", "当前账号没有编辑权限")
    return current_user


def require_owner(current_user: CurrentUser) -> User:
    if current_user.role != "OWNER":
        raise AppError(403, "PERMISSION_DENIED", "仅 Owner 可以执行此操作")
    return current_user


EditorUser = Annotated[User, Depends(require_editor)]
OwnerUser = Annotated[User, Depends(require_owner)]


def enforce_schedule_edit_lock(
    schedule_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: User,
) -> None:
    settings = get_settings()
    token = request.headers.get(settings.edit_lock_header_name)
    if not token:
        raise AppError(423, "EDIT_LOCK_TOKEN_REQUIRED", "请先获取此排表的编辑锁")
    require_edit_lock(db, schedule_id, current_user.id, token)
    request.state.edit_lock_token = token


def require_schedule_editor(
    schedule_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: EditorUser,
) -> User:
    enforce_schedule_edit_lock(schedule_id, request, db, current_user)
    return current_user


ScheduleEditor = Annotated[User, Depends(require_schedule_editor)]
