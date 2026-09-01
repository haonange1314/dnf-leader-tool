from app.schemas.dungeon import (
    CompanionPolicy,
    CompositionRule,
    CompositionRules,
    DungeonVersionDefinition,
    FormulaDefinition,
    MissingSlotPolicy,
    OptimizationRules,
    RoleType,
    SpecialRoleRule,
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
        description="内置 12 人团本：红黄绿三队，优先 3C1奶，每波一个红队秘宝 C。",
        version_no=2,
        default_wave_count=12,
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
        special_role_rules=SpecialRoleRules(
            rules=(
                SpecialRoleRule(
                    code="TREASURE_DAMAGE_CORE",
                    character_flag="TREASURE_DAMAGE",
                    count_per_wave=1,
                    target_team_key="RED",
                    companion_policy=CompanionPolicy(
                        role_type=RoleType.DAMAGE, objective="MINIMIZE_OTHER_MEMBER_SCORE"
                    ),
                ),
            )
        ),
        strength_order_rules=StrengthOrderRules(
            orders=(
                StrengthOrder(metric=RoleType.DAMAGE, teams=team_keys),
                StrengthOrder(metric=RoleType.BUFFER, teams=team_keys),
            )
        ),
        optimization_rules=OptimizationRules(
            balance_across_waves=(RoleType.DAMAGE, RoleType.BUFFER)
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
