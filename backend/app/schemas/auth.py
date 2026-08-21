import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

API_CONFIG = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)
UserRole = Literal["OWNER", "EDITOR", "VIEWER"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool


class UserCreate(BaseModel):
    model_config = API_CONFIG

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    role: UserRole
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = API_CONFIG

    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdate":
        if self.password is None and self.role is None and self.is_active is None:
            raise ValueError("至少修改一个账号字段")
        return self


class UserList(BaseModel):
    items: list[UserView]
    total: int


class AuditLogView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
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
