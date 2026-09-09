import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

API_CONFIG = ConfigDict(
    from_attributes=True,
    alias_generator=to_camel,
    populate_by_name=True,
    extra="forbid",
)


class BufferConversionRule(BaseModel):
    model_config = API_CONFIG

    profession: str = Field(min_length=1, max_length=80)
    multiplier: Decimal = Field(gt=0, le=10, decimal_places=5)

    @field_validator("profession")
    @classmethod
    def normalize_profession(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("职业不能为空")
        return normalized


class BufferConversionVersionCreate(BaseModel):
    model_config = API_CONFIG

    rules: list[BufferConversionRule] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_professions(self) -> "BufferConversionVersionCreate":
        keys = [rule.profession.strip().casefold() for rule in self.rules]
        if len(keys) != len(set(keys)):
            raise ValueError("职业不能重复")
        return self


class BufferConversionVersionView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    version: int
    rules: list[BufferConversionRule]
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime


class BufferConversionVersionList(BaseModel):
    items: list[BufferConversionVersionView]
    total: int


class BufferConversionPreview(BaseModel):
    model_config = API_CONFIG

    profession: str = Field(min_length=1, max_length=80)
    standing_score: Decimal = Field(ge=0, decimal_places=2)


class BufferConversionPreviewResult(BaseModel):
    model_config = API_CONFIG

    actual_score: Decimal
