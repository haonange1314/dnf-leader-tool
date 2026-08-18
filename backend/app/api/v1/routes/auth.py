from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_session_token,
    hash_session_token,
    session_expiry,
    utc_now,
    verify_password,
)
from app.models.identity import User, UserSession
from app.schemas.auth import LoginRequest, UserView

router = APIRouter()


@router.post("/login", response_model=UserView)
def login(payload: LoginRequest, response: Response, db: DbSession) -> User:
    settings = get_settings()
    username = payload.username.strip().casefold()
    user = db.scalar(select(User).where(User.username == username))
    if (
        user is None
        or not user.is_active
        or not verify_password(user.password_hash, payload.password)
    ):
        raise AppError(401, "INVALID_CREDENTIALS", "用户名或密码错误")

    token = create_session_token()
    now = utc_now()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=session_expiry(settings.session_ttl_hours),
            last_seen_at=now,
            created_at=now,
        )
    )
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession, current_user: CurrentUser) -> None:
    del current_user
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        session = db.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if session is not None:
            session.revoked_at = utc_now()
    response.delete_cookie(settings.session_cookie_name, path="/")
    db.commit()


@router.get("/me", response_model=UserView)
def me(current_user: CurrentUser, db: DbSession) -> User:
    db.commit()
    return current_user
