import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportChangeView(BaseModel):
    action: str
    player_name: str
    profession: str | None = None
    row_no: int | None = None
    fields: list[str] = Field(default_factory=list)


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
    change_details: list[ImportChangeView]
    rows: list[ImportRowView]


class ImportBatchSummaryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    total_rows: int
    summary: dict[str, int]
    created_at: datetime
    committed_at: datetime | None


class ImportBatchListView(BaseModel):
    items: list[ImportBatchSummaryView]
    total: int
