from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_session_token, utc_now
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
    session.last_seen_at = utc_now()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
