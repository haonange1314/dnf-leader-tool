import uuid

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, RoleReader, RoleWriter
from app.core.errors import AppError
from app.core.permissions import ALL_PERMISSION_CODES
from app.core.security import utc_now
from app.models.identity import Permission, Role, User, UserSession
from app.models.schedule import EditLock
from app.schemas.auth import (
    PermissionList,
    PermissionView,
    RoleCreate,
    RoleList,
    RoleUpdate,
    RoleView,
)

router = APIRouter()


def _role_view(role: Role, user_count: int) -> RoleView:
    return RoleView.model_validate(
        {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "is_active": role.is_active,
            "permission_codes": sorted(permission.code for permission in role.permissions),
            "user_count": user_count,
            "created_at": role.created_at,
            "updated_at": role.updated_at,
        }
    )


def _load_role(db: DbSession, role_id: uuid.UUID, *, for_update: bool = False) -> Role:
    statement = (
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    if for_update:
        statement = statement.with_for_update()
    role = db.scalar(statement)
    if role is None:
        raise AppError(404, "ROLE_NOT_FOUND", "角色不存在")
    return role


def _resolve_permissions(db: DbSession, codes: list[str]) -> list[Permission]:
    normalized = {code.strip().upper() for code in codes if code.strip()}
    unknown = sorted(normalized - ALL_PERMISSION_CODES)
    if unknown:
        raise AppError(
            422,
            "PERMISSION_NOT_FOUND",
            "包含系统不支持的权限",
            path="permissionCodes",
            details={"permissionCodes": unknown},
        )
    dependencies = {
        "DUNGEON_WRITE": {"DUNGEON_READ"},
        "ROSTER_WRITE": {"ROSTER_READ"},
        "ROSTER_IMPORT": {"ROSTER_READ"},
        "SCHEDULE_WRITE": {"SCHEDULE_READ"},
        "SCHEDULE_GENERATE": {"SCHEDULE_READ", "SCHEDULE_WRITE"},
        "SCHEDULE_PUBLISH": {"SCHEDULE_READ", "SCHEDULE_WRITE"},
        "SCHEDULE_EXPORT": {"SCHEDULE_READ"},
        "SHARE_MANAGE": {"SCHEDULE_READ"},
        "USER_WRITE": {"USER_READ", "ROLE_READ"},
        "ROLE_WRITE": {"ROLE_READ"},
    }
    missing = sorted(
        required
        for code in normalized
        for required in dependencies.get(code, set())
        if required not in normalized
    )
    if missing:
        raise AppError(
            422,
            "PERMISSION_DEPENDENCY_REQUIRED",
            "所选权限缺少必要的基础权限",
            path="permissionCodes",
            details={"permissionCodes": sorted(set(missing))},
        )
    permissions = list(
        db.scalars(select(Permission).where(Permission.code.in_(normalized)).order_by(Permission.code))
    )
    return permissions


@router.get("/permissions", response_model=PermissionList)
def list_permissions(db: DbSession, current_user: RoleReader) -> PermissionList:
    del current_user
    permissions = list(db.scalars(select(Permission).order_by(Permission.module, Permission.code)))
    return PermissionList(
        items=[
            PermissionView.model_validate(permission, from_attributes=True)
            for permission in permissions
        ],
        total=len(permissions),
    )


@router.get("/roles", response_model=RoleList)
def list_roles(
    db: DbSession,
    current_user: RoleReader,
    include_inactive: bool = Query(default=True, alias="includeInactive"),
) -> RoleList:
    del current_user
    statement = (
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.is_system.desc(), Role.code)
    )
    if not include_inactive:
        statement = statement.where(Role.is_active)
    roles = list(db.scalars(statement).unique())
    count_rows = db.execute(
        select(User.role_id, func.count(User.id)).group_by(User.role_id)
    ).all()
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in count_rows}
    return RoleList(
        items=[_role_view(role, counts.get(role.id, 0)) for role in roles],
        total=len(roles),
    )


@router.post("/roles", response_model=RoleView, status_code=201)
def create_role(payload: RoleCreate, db: DbSession, current_user: RoleWriter) -> RoleView:
    del current_user
    code = payload.code.strip().upper().replace("-", "_")
    role = Role(
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        is_system=False,
        is_active=payload.is_active,
        permissions=_resolve_permissions(db, payload.permission_codes),
    )
    db.add(role)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "ROLE_CODE_EXISTS", "角色编码已存在", path="code") from exc
    db.refresh(role)
    return _role_view(role, 0)


@router.patch("/roles/{role_id}", response_model=RoleView)
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    db: DbSession,
    current_user: RoleWriter,
) -> RoleView:
    del current_user
    role = _load_role(db, role_id, for_update=True)
    requested_permissions = (
        {code.strip().upper() for code in payload.permission_codes}
        if payload.permission_codes is not None
        else None
    )
    if role.code == "OWNER" and (
        (requested_permissions is not None and requested_permissions != ALL_PERMISSION_CODES)
        or payload.is_active is False
    ):
        raise AppError(
            409,
            "OWNER_ROLE_PROTECTED",
            "系统所有者角色必须保持启用并拥有全部权限",
        )
    if payload.is_active is False:
        active_users = db.scalar(
            select(func.count()).select_from(User).where(User.role_id == role.id, User.is_active)
        ) or 0
        if active_users:
            raise AppError(
                409,
                "ROLE_HAS_ACTIVE_USERS",
                "请先停用账号或为账号更换角色",
                details={"activeUserCount": active_users},
            )

    old_permissions = {permission.code for permission in role.permissions}
    old_active = role.is_active
    if payload.name is not None:
        role.name = payload.name.strip()
    if payload.description is not None:
        role.description = payload.description.strip() or None
    if payload.is_active is not None:
        role.is_active = payload.is_active
    if payload.permission_codes is not None:
        role.permissions = _resolve_permissions(db, payload.permission_codes)
    new_permissions = {permission.code for permission in role.permissions}
    access_changed = old_permissions != new_permissions or old_active != role.is_active
    if access_changed:
        user_ids = list(db.scalars(select(User.id).where(User.role_id == role.id)))
        if user_ids:
            db.execute(
                update(UserSession)
                .where(UserSession.user_id.in_(user_ids), UserSession.revoked_at.is_(None))
                .values(revoked_at=utc_now())
            )
            if "SCHEDULE_WRITE" not in new_permissions or not role.is_active:
                db.execute(delete(EditLock).where(EditLock.user_id.in_(user_ids)))
    db.commit()
    db.refresh(role)
    user_count = (
        db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)) or 0
    )
    return _role_view(role, user_count)
