import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class EditLockView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    schedule_id: uuid.UUID
    held: bool
    holder_user_id: uuid.UUID | None = None
    holder_username: str | None = None
    owned_by_current_user: bool = False
    can_takeover: bool = False
    acquired_at: datetime | None = None
    heartbeat_at: datetime | None = None
    expires_at: datetime | None = None
    heartbeat_interval_seconds: int
    token: str | None = None
