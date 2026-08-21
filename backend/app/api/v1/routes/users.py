import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DbSession, OwnerUser
from app.core.errors import AppError
from app.core.security import hash_password, normalize_username, utc_now
from app.models.identity import AuditLog, User, UserSession
from app.models.schedule import EditLock
from app.schemas.auth import AuditLogList, UserCreate, UserList, UserUpdate, UserView

router = APIRouter()


@router.get("/users", response_model=UserList)
def list_users(db: DbSession, current_user: OwnerUser) -> UserList:
    del current_user
    users = list(db.scalars(select(User).order_by(User.created_at, User.username)))
    return UserList(items=users, total=len(users))


@router.post("/users", response_model=UserView, status_code=201)
def create_user(payload: UserCreate, db: DbSession, current_user: OwnerUser) -> User:
    del current_user
    username = normalize_username(payload.username)
    if not username:
        raise AppError(422, "USERNAME_REQUIRED", "用户名不能为空", path="username")
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "USERNAME_EXISTS", "用户名已存在", path="username") from exc
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserView)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: DbSession,
    current_user: OwnerUser,
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "账号不存在")
    next_role = payload.role if payload.role is not None else user.role
    next_active = payload.is_active if payload.is_active is not None else user.is_active
    if user.id == current_user.id and not next_active:
        raise AppError(409, "CANNOT_DEACTIVATE_SELF", "不能停用当前登录账号")
    if user.role == "OWNER" and user.is_active and (next_role != "OWNER" or not next_active):
        active_owner_ids = list(
            db.scalars(
                select(User.id)
                .where(User.role == "OWNER", User.is_active)
                .order_by(User.id)
                .with_for_update()
            )
        )
        if len(active_owner_ids) <= 1:
            raise AppError(409, "LAST_OWNER_REQUIRED", "系统必须保留至少一个启用的 Owner")
    credentials_changed = payload.password is not None
    access_changed = next_role != user.role or next_active != user.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    user.role = next_role
    user.is_active = next_active
    if credentials_changed or access_changed:
        now = utc_now()
        current_session_id = getattr(request.state, "current_session_id", None)
        for session in db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
        ):
            keep_current_session = (
                user.id == current_user.id
                and session.id == current_session_id
                and next_active
            )
            if not keep_current_session:
                session.revoked_at = now
    if not next_active or next_role == "VIEWER":
        db.execute(delete(EditLock).where(EditLock.user_id == user.id))
    db.commit()
    db.refresh(user)
    return user


@router.get("/audit-logs", response_model=AuditLogList)
def list_audit_logs(
    db: DbSession,
    current_user: OwnerUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditLogList:
    del current_user
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = list(
        db.scalars(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return AuditLogList(items=rows, total=total)
