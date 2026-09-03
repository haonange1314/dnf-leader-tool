import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import DbSession, UserReader, UserWriter
from app.core.errors import AppError
from app.core.security import hash_password, normalize_username, utc_now
from app.models.identity import Role, User, UserSession
from app.models.schedule import EditLock
from app.schemas.auth import (
    ManagedUserView,
    RevokeSessionsResult,
    UserCreate,
    UserList,
    UserUpdate,
    UserView,
)

router = APIRouter()


def _load_role(db: DbSession, *, role_id: uuid.UUID | None, role_code: str | None) -> Role:
    statement = select(Role).options(selectinload(Role.permissions))
    if role_id is not None:
        statement = statement.where(Role.id == role_id)
    else:
        statement = statement.where(Role.code == (role_code or "").strip().upper())
    role = db.scalar(statement)
    if role is None:
        raise AppError(422, "ROLE_NOT_FOUND", "所选角色不存在", path="roleId")
    if not role.is_active:
        raise AppError(409, "ROLE_INACTIVE", "不能分配已停用的角色", path="roleId")
    return role


def _load_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.scalar(
        select(User)
        .options(selectinload(User.role_record).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "账号不存在")
    return user


def _managed_view(
    user: User, active_session_count: int, last_login_at: datetime | None
) -> ManagedUserView:
    return ManagedUserView.model_validate(
        {
            "id": user.id,
            "username": user.username,
            "role_id": user.role_id,
            "role": user.role,
            "role_name": user.role_name,
            "permissions": user.permissions,
            "is_active": user.is_active,
            "active_session_count": active_session_count,
            "last_login_at": last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
    )


@router.get("/users", response_model=UserList)
def list_users(
    db: DbSession,
    current_user: UserReader,
    search: str | None = Query(default=None, max_length=80),
    role_id: Annotated[uuid.UUID | None, Query(alias="roleId")] = None,
    is_active: bool | None = Query(default=None, alias="isActive"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> UserList:
    del current_user
    filters: list[ColumnElement[bool]] = []
    if search and search.strip():
        filters.append(User.username.ilike(f"%{search.strip()}%"))
    if role_id is not None:
        filters.append(User.role_id == role_id)
    if is_active is not None:
        filters.append(User.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    users = list(
        db.scalars(
            select(User)
            .options(selectinload(User.role_record).selectinload(Role.permissions))
            .where(*filters)
            .order_by(User.created_at.desc(), User.username)
            .offset(offset)
            .limit(limit)
        ).unique()
    )
    if not users:
        return UserList(items=[], total=total)
    user_ids = [user.id for user in users]
    now = utc_now()
    session_rows = db.execute(
        select(
            UserSession.user_id,
            func.count(UserSession.id)
            .filter(UserSession.revoked_at.is_(None), UserSession.expires_at > now)
            .label("active_count"),
            func.max(UserSession.created_at).label("last_login_at"),
        )
        .where(UserSession.user_id.in_(user_ids))
        .group_by(UserSession.user_id)
    ).all()
    session_by_user = {row.user_id: (row.active_count, row.last_login_at) for row in session_rows}
    return UserList(
        items=[_managed_view(user, *session_by_user.get(user.id, (0, None))) for user in users],
        total=total,
    )


@router.post("/users", response_model=UserView, status_code=201)
def create_user(payload: UserCreate, db: DbSession, current_user: UserWriter) -> User:
    del current_user
    username = normalize_username(payload.username)
    if not username:
        raise AppError(422, "USERNAME_REQUIRED", "用户名不能为空", path="username")
    role = _load_role(db, role_id=payload.role_id, role_code=payload.role)
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role_record=role,
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
    current_user: UserWriter,
) -> User:
    user = _load_user(db, user_id)
    next_role = (
        _load_role(db, role_id=payload.role_id, role_code=payload.role)
        if payload.role_id is not None or payload.role is not None
        else user.role_record
    )
    next_active = payload.is_active if payload.is_active is not None else user.is_active
    if user.id == current_user.id and not next_active:
        raise AppError(409, "CANNOT_DEACTIVATE_SELF", "不能停用当前登录账号")
    if user.id == current_user.id and next_role.id != user.role_id:
        raise AppError(409, "CANNOT_CHANGE_OWN_ROLE", "不能修改当前登录账号的角色")
    if user.role == "OWNER" and user.is_active and (next_role.code != "OWNER" or not next_active):
        active_owner_count = db.scalar(
            select(func.count())
            .select_from(User)
            .join(Role, User.role_id == Role.id)
            .where(Role.code == "OWNER", User.is_active, User.id != user.id)
        ) or 0
        if active_owner_count == 0:
            raise AppError(409, "LAST_OWNER_REQUIRED", "系统必须保留至少一个启用的系统所有者")

    credentials_changed = payload.password is not None
    access_changed = next_role.id != user.role_id or next_active != user.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    user.role_record = next_role
    user.is_active = next_active
    if credentials_changed or access_changed:
        _revoke_user_sessions(
            db,
            user,
            keep_session_id=(
                getattr(request.state, "current_session_id", None)
                if user.id == current_user.id and next_active
                else None
            ),
        )
    if not next_active or not next_role.has_permission("SCHEDULE_WRITE"):
        db.execute(delete(EditLock).where(EditLock.user_id == user.id))
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/revoke-sessions", response_model=RevokeSessionsResult)
def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: UserWriter,
) -> RevokeSessionsResult:
    user = _load_user(db, user_id)
    keep_session_id = (
        getattr(request.state, "current_session_id", None) if user.id == current_user.id else None
    )
    revoked_count = _revoke_user_sessions(db, user, keep_session_id=keep_session_id)
    db.execute(delete(EditLock).where(EditLock.user_id == user.id))
    db.commit()
    return RevokeSessionsResult(revoked_count=revoked_count)


def _revoke_user_sessions(
    db: DbSession, user: User, *, keep_session_id: uuid.UUID | None = None
) -> int:
    now = utc_now()
    sessions = list(
        db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    )
    revoked_count = 0
    for session in sessions:
        if keep_session_id is not None and session.id == keep_session_id:
            continue
        session.revoked_at = now
        revoked_count += 1
    return revoked_count
