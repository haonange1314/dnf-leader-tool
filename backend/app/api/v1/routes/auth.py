import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.application.identity_security import (
    add_audit_log,
    check_login_rate_limits,
    clear_login_failures,
    client_ip,
    login_limit_buckets,
    record_login_failure,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_csrf_token,
    create_session_token,
    hash_csrf_token,
    hash_password,
    hash_session_token,
    normalize_username,
    session_expiry,
    utc_now,
    verify_password,
)
from app.models.identity import User, UserSession
from app.schemas.auth import LoginRequest, UserView

router = APIRouter()
DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-used")


@router.post("/login", response_model=UserView)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    settings = get_settings()
    username = normalize_username(payload.username)
    ip_address = client_ip(request)
    limit_buckets = login_limit_buckets(username, ip_address, settings)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    try:
        check_login_rate_limits(db, limit_buckets, settings)
    except AppError:
        add_audit_log(
            db,
            action="AUTH_LOGIN",
            outcome="FAILURE",
            request_id=request_id,
            ip_address=ip_address,
            details={"username": username, "reason": "RATE_LIMITED"},
        )
        db.commit()
        raise
    user = db.scalar(select(User).where(User.username == username))
    password_valid = verify_password(
        user.password_hash if user is not None else DUMMY_PASSWORD_HASH,
        payload.password,
    )
    if user is None or not user.is_active or not user.role_record.is_active or not password_valid:
        attempts = record_login_failure(db, limit_buckets, settings)
        add_audit_log(
            db,
            action="AUTH_LOGIN",
            outcome="FAILURE",
            request_id=request_id,
            ip_address=ip_address,
            actor_user_id=user.id if user is not None else None,
            details={"username": username, "attemptCounts": attempts},
        )
        db.commit()
        raise AppError(401, "INVALID_CREDENTIALS", "用户名或密码错误")

    token = create_session_token()
    csrf_token = create_csrf_token()
    now = utc_now()
    clear_login_failures(db, limit_buckets)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            csrf_token_hash=hash_csrf_token(csrf_token),
            expires_at=session_expiry(settings.session_ttl_hours),
            last_seen_at=now,
            created_at=now,
        )
    )
    add_audit_log(
        db,
        action="AUTH_LOGIN",
        outcome="SUCCESS",
        request_id=request_id,
        ip_address=ip_address,
        actor_user_id=user.id,
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
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
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
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    db.commit()


@router.get("/me", response_model=UserView)
def me(current_user: CurrentUser, db: DbSession) -> User:
    db.commit()
    return current_user
