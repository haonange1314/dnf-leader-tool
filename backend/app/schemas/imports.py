import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ImportRowView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_no: int
    action: str
    payload: dict[str, Any]
    errors: list[dict[str, Any]]
    change_summary: str | None


class ImportBatchView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    total_rows: int
    summary: dict[str, int]
    created_at: datetime
    committed_at: datetime | None
    rows: list[ImportRowView]
