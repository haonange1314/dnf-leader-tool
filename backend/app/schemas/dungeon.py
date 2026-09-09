from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class RoleType(StrEnum):
    DAMAGE = "DAMAGE"
    BUFFER = "BUFFER"


PositiveSmallInt = Annotated[int, Field(gt=0, le=64)]
PositiveScale = Annotated[int, Field(gt=0, le=10_000)]
FROZEN_MODEL_CONFIG = ConfigDict(frozen=True, alias_generator=to_camel, populate_by_name=True)


class TeamDefinition(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    team_key: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=80)
    display_color: str = Field(min_length=1, max_length=20)
    display_order: int = Field(ge=0, le=7)
    member_count: PositiveSmallInt
    strength_rank: int | None = Field(default=None, gt=0, le=8)


class CompositionRule(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_]*$")
    applicable_team_keys: tuple[str, ...]
    roles: dict[RoleType, int]
    priority: PositiveSmallInt

    @model_validator(mode="after")
    def validate_roles(self) -> "CompositionRule":
        if not self.roles or any(count <= 0 for count in self.roles.values()):
            raise ValueError("组成规则必须包含至少一种角色且人数大于 0")
        return self


class CompositionRules(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal[1] = 1
    allowed: tuple[CompositionRule, ...]


class CompanionPolicy(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    role_type: RoleType
    objective: Literal["MINIMIZE_OTHER_MEMBER_SCORE"]


class SpecialRoleRule(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9_]*$")
    character_flag: Literal["TREASURE_DAMAGE"]
    count_per_wave: PositiveSmallInt
    target_team_key: str
    required_for_complete_wave: bool = True
    companion_policy: CompanionPolicy | None = None


class SpecialRoleRules(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal[1] = 1
    rules: tuple[SpecialRoleRule, ...] = ()


class StrengthOrder(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    metric: RoleType
    teams: tuple[str, ...]


class StrengthOrderRules(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal[1] = 1
    orders: tuple[StrengthOrder, ...] = ()


class BufferPlacementRule(BaseModel):
    """Versioned buffer distribution policy expressed with dungeon team keys."""

    model_config = FROZEN_MODEL_CONFIG

    mode: Literal["EXTRAS_BY_TEAM_THEN_WAVE"] = "EXTRAS_BY_TEAM_THEN_WAVE"
    team_order: tuple[str, ...]
    double_buffer_team_keys: tuple[str, ...]
    pair_extremes: bool = True


class DamagePlacementRule(BaseModel):
    """Versioned damage selection, pairing and team-balance policy."""

    model_config = FROZEN_MODEL_CONFIG

    mode: Literal["PRIMARY_THEN_BALANCE"] = "PRIMARY_THEN_BALANCE"
    primary_team_key: str
    balanced_team_keys: tuple[str, ...]
    pair_extremes_in_double_buffer_teams: bool = True


class OptimizationRules(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal[1] = 1
    balance_across_waves: tuple[RoleType, ...] = ()
    respect_player_preferences: bool = True
    buffer_placement: BufferPlacementRule | None = None
    damage_placement: DamagePlacementRule | None = None


class MissingSlotPolicy(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal[1] = 1
    mode: Literal["FILL_EARLIER_WAVES", "SPREAD_EVENLY"]


class FormulaDefinition(BaseModel):
    model_config = FROZEN_MODEL_CONFIG

    code: str
    version: PositiveSmallInt
    damage_unit: Literal["YI"] = "YI"
    damage_scale: PositiveScale = 100
    buffer_scale: PositiveScale = 10
    team_damage_mode: Literal["SUM"] = "SUM"
    two_buffer_mode: Literal["SUM"] = "SUM"


class DungeonVersionDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    dungeon_code: str = Field(min_length=1, max_length=80)
    dungeon_name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    version_no: PositiveSmallInt = 1
    default_wave_count: PositiveSmallInt
    min_wave_count: PositiveSmallInt
    max_wave_count: PositiveSmallInt | None = None
    formula: FormulaDefinition
    teams: tuple[TeamDefinition, ...]
    composition_rules: CompositionRules
    special_role_rules: SpecialRoleRules
    strength_order_rules: StrengthOrderRules
    optimization_rules: OptimizationRules
    missing_slot_policy: MissingSlotPolicy

    @property
    def participants_per_wave(self) -> int:
        return sum(team.member_count for team in self.teams)

    @model_validator(mode="after")
    def validate_definition(self) -> "DungeonVersionDefinition":
        if not self.teams:
            raise ValueError("副本版本必须至少包含一支队伍")
        if self.participants_per_wave > 64:
            raise ValueError("副本每波总人数不能超过 64")
        if self.max_wave_count is not None and self.max_wave_count < self.min_wave_count:
            raise ValueError("最大波数不能小于最小波数")
        if self.default_wave_count < self.min_wave_count or (
            self.max_wave_count is not None and self.default_wave_count > self.max_wave_count
        ):
            raise ValueError("默认波数必须处于允许范围")

        team_by_key = {team.team_key: team for team in self.teams}
        if len(team_by_key) != len(self.teams):
            raise ValueError("队伍 key 必须唯一")
        if len({team.display_order for team in self.teams}) != len(self.teams):
            raise ValueError("队伍展示顺序必须唯一")
        strength_ranks = [
            team.strength_rank for team in self.teams if team.strength_rank is not None
        ]
        if len(strength_ranks) != len(set(strength_ranks)):
            raise ValueError("已填写的队伍强度排名必须唯一")
        balance_metrics = self.optimization_rules.balance_across_waves
        if len(balance_metrics) != len(set(balance_metrics)):
            raise ValueError("跨波平衡指标必须唯一")
        buffer_placement = self.optimization_rules.buffer_placement
        if buffer_placement is not None:
            if len(buffer_placement.team_order) != len(set(buffer_placement.team_order)):
                raise ValueError("奶排队规则中的队伍顺序不能重复")
            if len(buffer_placement.double_buffer_team_keys) != len(
                set(buffer_placement.double_buffer_team_keys)
            ):
                raise ValueError("奶排队规则中的双奶队伍不能重复")
            unknown = {
                *buffer_placement.team_order,
                *buffer_placement.double_buffer_team_keys,
            } - team_by_key.keys()
            if unknown:
                raise ValueError(f"奶排队规则引用未知队伍: {sorted(unknown)}")
            if set(buffer_placement.team_order) != team_by_key.keys():
                raise ValueError("奶排队规则的队伍顺序必须覆盖全部队伍")
            if not set(buffer_placement.double_buffer_team_keys) <= set(
                buffer_placement.team_order
            ):
                raise ValueError("双奶队伍必须包含在奶排队顺序中")

        damage_placement = self.optimization_rules.damage_placement
        if damage_placement is not None:
            if len(damage_placement.balanced_team_keys) < 2:
                raise ValueError("C 平衡规则至少需要两支队伍")
            if len(damage_placement.balanced_team_keys) != len(
                set(damage_placement.balanced_team_keys)
            ):
                raise ValueError("C 平衡规则中的队伍不能重复")
            unknown = {
                damage_placement.primary_team_key,
                *damage_placement.balanced_team_keys,
            } - team_by_key.keys()
            if unknown:
                raise ValueError(f"C 排队规则引用未知队伍: {sorted(unknown)}")
            if damage_placement.primary_team_key in damage_placement.balanced_team_keys:
                raise ValueError("C 主队不能同时作为平衡队伍")

        covered: set[str] = set()
        composition_codes = [rule.code for rule in self.composition_rules.allowed]
        if len(composition_codes) != len(set(composition_codes)):
            raise ValueError("组成规则 code 必须唯一")
        for rule in self.composition_rules.allowed:
            if len(rule.applicable_team_keys) != len(set(rule.applicable_team_keys)):
                raise ValueError(f"组成规则 {rule.code} 的适用队伍不能重复")
            unknown = set(rule.applicable_team_keys) - team_by_key.keys()
            if unknown:
                raise ValueError(f"组成规则引用未知队伍: {sorted(unknown)}")
            for team_key in rule.applicable_team_keys:
                if sum(rule.roles.values()) != team_by_key[team_key].member_count:
                    raise ValueError(f"组成规则 {rule.code} 人数与队伍 {team_key} 容量不一致")
                covered.add(team_key)
        if covered != team_by_key.keys():
            raise ValueError("每支队伍必须至少有一条适用组成规则")

        if buffer_placement is not None:
            for team_key in buffer_placement.team_order:
                buffer_counts = {
                    rule.roles.get(RoleType.BUFFER, 0)
                    for rule in self.composition_rules.allowed
                    if team_key in rule.applicable_team_keys
                }
                if not buffer_counts or min(buffer_counts) <= 0:
                    raise ValueError(f"奶排队规则的队伍 {team_key} 缺少单奶组成")
                if (
                    team_key in buffer_placement.double_buffer_team_keys
                    and max(buffer_counts) < min(buffer_counts) + 1
                ):
                    raise ValueError(f"奶排队规则的队伍 {team_key} 缺少双奶组成")

        if damage_placement is not None:
            for team_key in {
                damage_placement.primary_team_key,
                *damage_placement.balanced_team_keys,
            }:
                if not any(
                    team_key in rule.applicable_team_keys
                    and rule.roles.get(RoleType.DAMAGE, 0) > 0
                    for rule in self.composition_rules.allowed
                ):
                    raise ValueError(f"C 排队规则的队伍 {team_key} 缺少含 C 的组成")

        special_codes = [rule.code for rule in self.special_role_rules.rules]
        if len(special_codes) != len(set(special_codes)):
            raise ValueError("特殊角色规则 code 必须唯一")
        for special_rule in self.special_role_rules.rules:
            if special_rule.target_team_key not in team_by_key:
                raise ValueError(f"特殊角色规则引用未知队伍: {special_rule.target_team_key}")
            if special_rule.count_per_wave > team_by_key[special_rule.target_team_key].member_count:
                raise ValueError(f"特殊角色规则 {special_rule.code} 数量超过目标队伍容量")
        order_metrics = [order.metric for order in self.strength_order_rules.orders]
        if len(order_metrics) != len(set(order_metrics)):
            raise ValueError("同一种强度指标只能配置一条顺序规则")
        for order in self.strength_order_rules.orders:
            if not order.teams:
                raise ValueError("强度顺序必须至少包含一支队伍")
            if len(order.teams) != len(set(order.teams)):
                raise ValueError("强度顺序中的队伍不能重复")
            unknown = set(order.teams) - team_by_key.keys()
            if unknown:
                raise ValueError(f"强度顺序引用未知队伍: {sorted(unknown)}")
        return self
