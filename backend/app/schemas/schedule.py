import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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


class ScheduleUpdate(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=2000)
    wave_count: int | None = Field(default=None, gt=0, le=MAX_WAVE_COUNT)
    confirm_wave_reduction: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("排表名称不能为空")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ScheduleUpdate":
        if not ({"name", "note", "wave_count"} & self.model_fields_set):
            raise ValueError("至少修改名称、备注或波数之一")
        return self


class ScheduleCopyPreviewRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    target_dungeon_version_id: uuid.UUID | None = None
    wave_count: int | None = Field(default=None, gt=0, le=MAX_WAVE_COUNT)


class ScheduleCopy(ScheduleCopyPreviewRequest):
    name: str = Field(min_length=1, max_length=160)
    migration_fingerprint: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]+$"
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("排表名称不能为空")
        return normalized


class ScheduleCopyChange(BaseModel):
    model_config = CFG

    code: str
    description: str
    before: Any | None = None
    after: Any | None = None


class ScheduleCopyPreview(BaseModel):
    model_config = CFG

    revision: int
    source_dungeon_version_id: uuid.UUID
    target_dungeon_version_id: uuid.UUID
    wave_count: int
    migration_required: bool
    migration_fingerprint: str
    changes: list[ScheduleCopyChange]


class ScheduleParticipantsUpdate(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    selected_participant_ids: list[uuid.UUID] = Field(max_length=5000)

    @field_validator("selected_participant_ids")
    @classmethod
    def validate_unique_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("参团角色 ID 不能重复")
        return value


class PlayerPreferenceInput(BaseModel):
    model_config = CFG

    player_id: uuid.UUID
    allowed_waves: list[int] | None = None
    max_wave_count: int | None = Field(default=None, gt=0, le=MAX_WAVE_COUNT)
    prefer_early: bool = False
    prefer_contiguous: bool = False

    @field_validator("allowed_waves")
    @classmethod
    def normalize_allowed_waves(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(wave_no <= 0 for wave_no in value):
            raise ValueError("可用波次必须大于 0")
        if len(value) != len(set(value)):
            raise ValueError("可用波次不能重复")
        return sorted(value)


class SchedulePreferencesUpdate(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    preferences: list[PlayerPreferenceInput] = Field(max_length=5000)

    @model_validator(mode="after")
    def validate_unique_players(self) -> "SchedulePreferencesUpdate":
        player_ids = [preference.player_id for preference in self.preferences]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("玩家偏好不能重复")
        return self


class ScheduleSyncChange(BaseModel):
    model_config = CFG

    action: str
    character_id: uuid.UUID
    player_name: str
    character_name: str
    changed_fields: list[str]


class ScheduleSyncPreview(BaseModel):
    model_config = CFG

    revision: int
    source_fingerprint: str
    changes: list[ScheduleSyncChange]
    summary: dict[str, int]


class ScheduleSyncCommit(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    source_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")


class ScheduleSummary(BaseModel):
    model_config = CFG
    id: uuid.UUID
    name: str
    dungeon_version_id: uuid.UUID
    wave_count: int
    status: str
    revision: int
    validation_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class SlotView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    slot_no: int
    participant_id: uuid.UUID | None
    is_locked: bool


class SpecialAssignmentView(BaseModel):
    model_config = CFG

    id: uuid.UUID
    rule_code: str
    participant_id: uuid.UUID
    target_team_key_snapshot: str


class TeamView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    team_key: str
    display_name_snapshot: str
    display_color_snapshot: str
    display_order_snapshot: int
    member_count_snapshot: int
    strength_rank_snapshot: int | None
    damage_total: Any
    buffer_total: Any
    composition_code: str
    slots: list[SlotView]


class WaveView(BaseModel):
    model_config = CFG
    id: uuid.UUID
    wave_no: int
    is_locked: bool
    damage_total: Any
    buffer_total: Any
    teams: list[TeamView]
    special_assignments: list[SpecialAssignmentView]


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
    is_locked: bool
    unassigned_reason: dict[str, Any] | None


class PlayerPreferenceView(BaseModel):
    model_config = CFG

    player_id: uuid.UUID
    allowed_waves: list[int] | None
    max_wave_count: int | None
    prefer_early: bool
    prefer_contiguous: bool


class ScheduleDetail(ScheduleSummary):
    note: str | None
    participants: list[ParticipantView]
    preferences: list[PlayerPreferenceView]
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


class ValidationRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)


class GenerationRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    preserve_locks: bool = True
    random_seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    time_limit_seconds: int | None = Field(default=None, ge=1, le=60)


class GenerationRunView(BaseModel):
    model_config = CFG

    id: uuid.UUID
    schedule_id: uuid.UUID
    input_revision: int
    result_revision: int | None
    status: str
    input_hash: str
    solver_version: str
    formula_version_id: uuid.UUID
    random_seed: int
    time_limit_seconds: int
    duration_ms: int | None
    objective_summary: dict[str, Any] | None
    diagnostics: dict[str, Any] | None
    created_at: datetime
    finished_at: datetime | None


class GenerationRunList(BaseModel):
    items: list[GenerationRunView]
    total: int


class GenerationResponse(BaseModel):
    model_config = CFG

    run: GenerationRunView
    schedule: ScheduleDetail
