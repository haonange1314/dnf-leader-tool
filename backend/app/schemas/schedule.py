import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.domain.schedule import MAX_WAVE_COUNT

CFG = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class ScheduleCreate(BaseModel):
    model_config = CFG
    name: str = Field(min_length=1, max_length=160)
    dungeon_version_id: uuid.UUID
    wave_count: int | None = Field(default=None, gt=0, le=MAX_WAVE_COUNT)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("排表名称不能为空")
        return normalized


class ScheduleSummary(BaseModel):
    model_config = CFG
    id: uuid.UUID
    name: str
    dungeon_version_id: uuid.UUID
    wave_count: int
    status: str
    revision: int
    validation_summary: dict[str, Any] | None


class SlotView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    slot_no: int
    participant_id: uuid.UUID | None
    is_locked: bool


class TeamView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    team_key: str
    display_name_snapshot: str
    display_color_snapshot: str
    member_count_snapshot: int
    slots: list[SlotView]


class WaveView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    wave_no: int
    is_locked: bool
    teams: list[TeamView]


class ParticipantView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    character_id: uuid.UUID
    player_id_snapshot: uuid.UUID
    player_name_snapshot: str
    character_name_snapshot: str
    profession_snapshot: str
    role_type_snapshot: str
    damage_score_snapshot: Any | None
    buffer_score_snapshot: Any | None
    is_treasure_snapshot: bool
    is_selected: bool


class ScheduleDetail(ScheduleSummary):
    participants: list[ParticipantView]
    waves: list[WaveView]


class ScheduleList(BaseModel):
    items: list[ScheduleSummary]
    total: int


class IssueView(BaseModel):
    severity: str
    code: str
    message_params: dict[str, Any]


class ValidationReport(BaseModel):
    revision: int
    issues: list[IssueView]
    summary: dict[str, int]
