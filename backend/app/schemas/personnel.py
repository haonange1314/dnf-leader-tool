import uuid
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

API_CONFIG = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class CharacterRole(StrEnum):
    DAMAGE = "DAMAGE"
    BUFFER = "BUFFER"


class CharacterFields(BaseModel):
    model_config = API_CONFIG

    profession: str = Field(min_length=1, max_length=80)
    role_type: CharacterRole
    damage_score: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    buffer_score: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    is_treasure_damage: bool = False
    is_fixed_lead_team_buffer: bool = False
    is_group_hunt: bool = False
    default_raid_participant: bool = True
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_scores(self) -> "CharacterFields":
        if self.role_type == CharacterRole.DAMAGE:
            if self.damage_score is None or self.buffer_score is not None:
                raise ValueError("C 必须填写伤害且不能填写奶评分")
            if self.damage_score != self.damage_score.to_integral_value():
                raise ValueError("C 伤害必须为整数")
        elif self.buffer_score is None or self.damage_score is not None:
            raise ValueError("奶必须填写增益评分且不能填写伤害")
        if self.is_treasure_damage and self.role_type != CharacterRole.DAMAGE:
            raise ValueError("只有 C 可以标记为秘宝 C")
        if self.is_fixed_lead_team_buffer and self.role_type != CharacterRole.BUFFER:
            raise ValueError("只有奶可以标记为固定红队奶")
        if self.is_group_hunt and self.role_type != CharacterRole.DAMAGE:
            raise ValueError("只有 C 可以标记为群猎")
        return self


class CharacterCreate(CharacterFields):
    pass


class CharacterUpdate(CharacterFields):
    pass


class CharacterView(CharacterFields):
    id: uuid.UUID
    player_id: uuid.UUID
    sort_order: int = Field(ge=0)


class PlayerCreate(BaseModel):
    model_config = API_CONFIG

    display_name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    characters: list[CharacterCreate] = []


class PlayerUpdate(BaseModel):
    model_config = API_CONFIG

    display_name: str = Field(min_length=1, max_length=120)
    is_active: bool


class PlayerView(BaseModel):
    model_config = API_CONFIG

    id: uuid.UUID
    display_name: str
    is_active: bool
    sort_order: int = Field(ge=0)
    characters: list[CharacterView]


class PlayerList(BaseModel):
    items: list[PlayerView]
    total: int


class CharacterBatchUpdate(BaseModel):
    model_config = API_CONFIG

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    is_active: bool | None = None
    default_raid_participant: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CharacterBatchUpdate":
        if self.is_active is None and self.default_raid_participant is None:
            raise ValueError("至少选择一个批量修改字段")
        if len(self.ids) != len(set(self.ids)):
            raise ValueError("角色 ID 不能重复")
        return self


class BatchUpdateResult(BaseModel):
    updated: int


class PersonnelReorder(BaseModel):
    model_config = API_CONFIG

    ordered_ids: list[uuid.UUID] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "PersonnelReorder":
        if len(self.ordered_ids) != len(set(self.ordered_ids)):
            raise ValueError("排序 ID 不能重复")
        return self
