from app.schemas.dungeon import (
    BufferPlacementRule,
    CompositionRule,
    CompositionRules,
    DamagePlacementRule,
    DungeonVersionDefinition,
    FormulaDefinition,
    MissingSlotPolicy,
    OptimizationRules,
    RoleType,
    SpecialRoleRules,
    StrengthOrder,
    StrengthOrderRules,
    TeamDefinition,
)

TEAM_SCORE_V1 = FormulaDefinition(code="TEAM_SCORE", version=1)
TEAM_SCORE_V2 = FormulaDefinition(code="TEAM_SCORE", version=2, buffer_scale=100)


def builtin_raid_12_definition() -> DungeonVersionDefinition:
    team_keys = ("RED", "YELLOW", "GREEN")
    return DungeonVersionDefinition(
        dungeon_code="BUILTIN_RAID_12",
        dungeon_name="12 人团本",
        description=(
            "内置 12 人团本：先按实际奶量安排红黄双奶与首尾配对，"
            "再将强 C 优先放入红队并平衡黄绿队平均伤害。"
        ),
        version_no=5,
        default_wave_count=13,
        min_wave_count=1,
        max_wave_count=50,
        formula=TEAM_SCORE_V2,
        teams=(
            TeamDefinition(
                team_key="RED",
                display_name="红队",
                display_color="#e5484d",
                display_order=0,
                member_count=4,
                strength_rank=1,
            ),
            TeamDefinition(
                team_key="YELLOW",
                display_name="黄队",
                display_color="#f5a524",
                display_order=1,
                member_count=4,
                strength_rank=2,
            ),
            TeamDefinition(
                team_key="GREEN",
                display_name="绿队",
                display_color="#30a46c",
                display_order=2,
                member_count=4,
                strength_rank=3,
            ),
        ),
        composition_rules=CompositionRules(
            allowed=(
                CompositionRule(
                    code="3D1B",
                    applicable_team_keys=team_keys,
                    roles={RoleType.DAMAGE: 3, RoleType.BUFFER: 1},
                    priority=1,
                ),
                CompositionRule(
                    code="2D2B",
                    applicable_team_keys=team_keys,
                    roles={RoleType.DAMAGE: 2, RoleType.BUFFER: 2},
                    priority=2,
                ),
            )
        ),
        special_role_rules=SpecialRoleRules(),
        strength_order_rules=StrengthOrderRules(
            orders=(
                StrengthOrder(metric=RoleType.BUFFER, teams=team_keys),
            )
        ),
        optimization_rules=OptimizationRules(
            balance_across_waves=(RoleType.DAMAGE, RoleType.BUFFER),
            buffer_placement=BufferPlacementRule(
                team_order=team_keys,
                double_buffer_team_keys=("RED", "YELLOW"),
            ),
            damage_placement=DamagePlacementRule(
                primary_team_key="RED",
                balanced_team_keys=("YELLOW", "GREEN"),
            ),
        ),
        missing_slot_policy=MissingSlotPolicy(mode="FILL_EARLIER_WAVES"),
    )


def custom_party_4_definition() -> DungeonVersionDefinition:
    return DungeonVersionDefinition(
        dungeon_code="POC_PARTY_4",
        dungeon_name="自定义单队 4 人副本",
        description="仅供通用建模 PoC 使用，不写入内置生产种子。",
        default_wave_count=1,
        min_wave_count=1,
        max_wave_count=12,
        formula=TEAM_SCORE_V1,
        teams=(
            TeamDefinition(
                team_key="PARTY",
                display_name="队伍",
                display_color="#3e63dd",
                display_order=0,
                member_count=4,
            ),
        ),
        composition_rules=CompositionRules(
            allowed=(
                CompositionRule(
                    code="3D1B",
                    applicable_team_keys=("PARTY",),
                    roles={RoleType.DAMAGE: 3, RoleType.BUFFER: 1},
                    priority=1,
                ),
            )
        ),
        special_role_rules=SpecialRoleRules(),
        strength_order_rules=StrengthOrderRules(),
        optimization_rules=OptimizationRules(balance_across_waves=()),
        missing_slot_policy=MissingSlotPolicy(mode="FILL_EARLIER_WAVES"),
    )
