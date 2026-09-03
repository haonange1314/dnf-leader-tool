import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

API_CONFIG = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role_id: uuid.UUID
    role: str
    role_name: str
    permissions: list[str]
    is_active: bool


class UserCreate(BaseModel):
    model_config = API_CONFIG

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    role_id: uuid.UUID | None = None
    role: str | None = Field(default=None, min_length=1, max_length=40)
    is_active: bool = True

    @model_validator(mode="after")
    def require_role(self) -> "UserCreate":
        if self.role_id is None and self.role is None:
            raise ValueError("必须选择角色")
        return self


class UserUpdate(BaseModel):
    model_config = API_CONFIG

    password: str | None = Field(default=None, min_length=10, max_length=256)
    role_id: uuid.UUID | None = None
    role: str | None = Field(default=None, min_length=1, max_length=40)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdate":
        if (
            self.password is None
            and self.role_id is None
            and self.role is None
            and self.is_active is None
        ):
            raise ValueError("至少修改一个账号字段")
        return self


class ManagedUserView(UserView):
    model_config = ConfigDict(from_attributes=True)

    active_session_count: int
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserList(BaseModel):
    items: list[ManagedUserView]
    total: int


class RevokeSessionsResult(BaseModel):
    model_config = API_CONFIG

    revoked_count: int


class PermissionView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    code: str
    name: str
    module: str
    description: str | None


class RoleView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    permission_codes: list[str]
    user_count: int
    created_at: datetime
    updated_at: datetime


class RoleList(BaseModel):
    items: list[RoleView]
    total: int


class PermissionList(BaseModel):
    items: list[PermissionView]
    total: int


class RoleCreate(BaseModel):
    model_config = API_CONFIG

    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: list[str] = Field(default_factory=list, max_length=100)
    is_active: bool = True


class RoleUpdate(BaseModel):
    model_config = API_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: list[str] | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_role_change(self) -> "RoleUpdate":
        if all(
            value is None
            for value in (self.name, self.description, self.permission_codes, self.is_active)
        ):
            raise ValueError("至少修改一个角色字段")
        return self


class AuditLogView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_username: str | None = None
    action: str
    outcome: str
    request_id: str
    ip_address: str | None
    resource_type: str | None
    resource_id: str | None
    details: dict[str, object]
    created_at: datetime


class AuditLogList(BaseModel):
    items: list[AuditLogView]
    total: int
