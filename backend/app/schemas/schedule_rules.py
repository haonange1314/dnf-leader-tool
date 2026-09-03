from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic.alias_generators import to_camel

CFG = ConfigDict(
    from_attributes=True,
    alias_generator=to_camel,
    populate_by_name=True,
    extra="forbid",
)


class RuleReference(BaseModel):
    model_config = CFG

    text: str = Field(min_length=1, max_length=120)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("规则引用不能为空")
        return normalized


class WaveRange(BaseModel):
    model_config = CFG

    start: int = Field(gt=0)
    end: int = Field(gt=0)

    @field_validator("end")
    @classmethod
    def validate_end(cls, value: int, info: ValidationInfo) -> int:
        start = info.data.get("start")
        if isinstance(start, int) and value < start:
            raise ValueError("波次范围结束值不能小于开始值")
        return value


class RuleCandidateBase(BaseModel):
    model_config = CFG

    candidate_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    explanation: str = Field(min_length=1, max_length=300)

    @field_validator("candidate_id", mode="before")
    @classmethod
    def normalize_numeric_candidate_id(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value


class PlayerAllowedWavesCandidate(RuleCandidateBase):
    type: Literal["PLAYER_ALLOWED_WAVES"]
    enforcement: Literal["HARD"]
    player_reference: RuleReference
    waves: list[int] = Field(min_length=1, max_length=50)


class PlayerForbiddenWavesCandidate(RuleCandidateBase):
    type: Literal["PLAYER_FORBIDDEN_WAVES"]
    enforcement: Literal["HARD"]
    player_reference: RuleReference
    waves: list[int] = Field(min_length=1, max_length=50)


class PlayersNotSameWaveCandidate(RuleCandidateBase):
    type: Literal["PLAYERS_NOT_SAME_WAVE"]
    enforcement: Literal["HARD"]
    player_references: list[RuleReference] = Field(min_length=2, max_length=20)


class CharacterRequiredWaveCandidate(RuleCandidateBase):
    type: Literal["CHARACTER_REQUIRED_WAVE"]
    enforcement: Literal["HARD"]
    character_reference: RuleReference
    player_reference: RuleReference | None = None
    wave_no: int = Field(gt=0)


class CharacterRequiredTeamCandidate(RuleCandidateBase):
    type: Literal["CHARACTER_REQUIRED_TEAM"]
    enforcement: Literal["HARD"]
    character_reference: RuleReference
    player_reference: RuleReference | None = None
    team_reference: RuleReference


class PlayerPreferWaveRangeCandidate(RuleCandidateBase):
    type: Literal["PLAYER_PREFER_WAVE_RANGE"]
    enforcement: Literal["SOFT"]
    player_reference: RuleReference
    wave_range: WaveRange


class PlayerPreferContiguousCandidate(RuleCandidateBase):
    type: Literal["PLAYER_PREFER_CONTIGUOUS"]
    enforcement: Literal["SOFT"]
    player_reference: RuleReference


class CharacterPreferTeamCandidate(RuleCandidateBase):
    type: Literal["CHARACTER_PREFER_TEAM"]
    enforcement: Literal["SOFT"]
    character_reference: RuleReference
    player_reference: RuleReference | None = None
    team_reference: RuleReference


RuleCandidate = Annotated[
    PlayerAllowedWavesCandidate
    | PlayerForbiddenWavesCandidate
    | PlayersNotSameWaveCandidate
    | CharacterRequiredWaveCandidate
    | CharacterRequiredTeamCandidate
    | PlayerPreferWaveRangeCandidate
    | PlayerPreferContiguousCandidate
    | CharacterPreferTeamCandidate,
    Field(discriminator="type"),
]


class RuleProviderOutput(BaseModel):
    model_config = CFG

    schema_version: Literal[1]
    rules: list[RuleCandidate] = Field(default_factory=list, max_length=50)
    unsupported_items: list[str] = Field(default_factory=list, max_length=20)


class ScheduleRuleSetParseRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    source_text: str = Field(min_length=1, max_length=10_000)

    @field_validator("source_text")
    @classmethod
    def normalize_source_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("本次排表要求不能为空")
        return normalized


class ScheduleRuleSetConfirmRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)
    source_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
    context_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")


class ScheduleRuleSetClearRequest(BaseModel):
    model_config = CFG

    base_revision: int = Field(gt=0)


class RuleResolutionIssueView(BaseModel):
    model_config = CFG

    code: str
    candidate_id: str | None
    field: str | None
    reference: str | None
    matches: list[str]


class ScheduleRuleSetView(BaseModel):
    model_config = CFG

    id: uuid.UUID
    schedule_id: uuid.UUID
    input_revision: int
    source_text: str
    source_hash: str
    context_hash: str
    status: Literal["PARSED", "CONFIRMED", "STALE", "SUPERSEDED", "FAILED"]
    model_provider: str
    model_name: str
    provider_response_id: str | None
    prompt_version: str
    schema_version: int
    parsed_rules: list[dict[str, Any]]
    resolved_references: dict[str, Any]
    issues: list[RuleResolutionIssueView]
    created_by: uuid.UUID
    confirmed_by: uuid.UUID | None
    created_at: datetime
    confirmed_at: datetime | None


class ScheduleRuleSetList(BaseModel):
    model_config = CFG

    items: list[ScheduleRuleSetView]
    total: int
    active_rule_set_id: uuid.UUID | None
    revision: int
    max_source_chars: int
    parsing_enabled: bool


class ScheduleRuleSetMutationResponse(BaseModel):
    model_config = CFG

    revision: int
    active_rule_set_id: uuid.UUID | None
    rule_set: ScheduleRuleSetView | None
