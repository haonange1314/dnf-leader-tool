import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.dungeon import (
    CompositionRules,
    FormulaDefinition,
    MissingSlotPolicy,
    OptimizationRules,
    SpecialRoleRules,
    StrengthOrderRules,
    TeamDefinition,
)

API_CONFIG = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class DungeonCreate(BaseModel):
    model_config = API_CONFIG

    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class DungeonUpdate(BaseModel):
    model_config = API_CONFIG

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool


class DungeonVersionInput(BaseModel):
    model_config = API_CONFIG

    default_wave_count: int = Field(gt=0, le=50)
    min_wave_count: int = Field(gt=0, le=50)
    max_wave_count: int | None = Field(default=None, gt=0, le=50)
    formula: FormulaDefinition
    teams: tuple[TeamDefinition, ...]
    composition_rules: CompositionRules
    special_role_rules: SpecialRoleRules
    strength_order_rules: StrengthOrderRules
    optimization_rules: OptimizationRules
    missing_slot_policy: MissingSlotPolicy


class TeamView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    team_key: str
    display_name: str
    display_color: str
    display_order: int
    member_count: int
    strength_rank: int | None


class DungeonVersionView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    dungeon_id: uuid.UUID
    version_no: int
    status: str
    default_wave_count: int
    min_wave_count: int
    max_wave_count: int | None
    formula: FormulaDefinition
    teams: list[TeamView]
    composition_rules: dict[str, object]
    special_role_rules: dict[str, object]
    strength_order_rules: dict[str, object]
    optimization_rules: dict[str, object]
    missing_slot_policy: dict[str, object]
    created_at: datetime
    published_at: datetime | None


class DungeonSummary(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    versions: list[DungeonVersionView]


class DungeonList(BaseModel):
    items: list[DungeonSummary]
    total: int


class ValidationResult(BaseModel):
    valid: bool
    issues: list[str]
