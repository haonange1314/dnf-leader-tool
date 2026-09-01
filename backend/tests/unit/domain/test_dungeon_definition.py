import pytest
from pydantic import ValidationError

from app.domain.dungeon import builtin_raid_12_definition, custom_party_4_definition


def test_builtin_raid_is_versioned_and_capacity_is_derived() -> None:
    definition = builtin_raid_12_definition()

    assert definition.dungeon_code == "BUILTIN_RAID_12"
    assert definition.default_wave_count == 12
    assert definition.participants_per_wave == 12
    assert [team.team_key for team in definition.teams] == ["RED", "YELLOW", "GREEN"]
    assert [rule.code for rule in definition.composition_rules.allowed] == ["3D1B", "2D2B"]
    assert definition.special_role_rules.rules[0].target_team_key == "RED"


def test_custom_party_proves_team_count_and_capacity_are_not_fixed() -> None:
    definition = custom_party_4_definition()

    assert definition.participants_per_wave == 4
    assert len(definition.teams) == 1
    assert definition.teams[0].team_key == "PARTY"
    assert definition.special_role_rules.rules == ()


def test_definition_rejects_composition_capacity_mismatch() -> None:
    payload = builtin_raid_12_definition().model_dump()
    payload["teams"][0]["member_count"] = 5

    with pytest.raises(ValidationError, match="容量不一致"):
        type(builtin_raid_12_definition()).model_validate(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["composition_rules"].update(
                {
                    "allowed": payload["composition_rules"]["allowed"]
                    + (payload["composition_rules"]["allowed"][0].copy(),)
                }
            ),
            "组成规则 code 必须唯一",
        ),
        (
            lambda payload: payload["special_role_rules"].update(
                {
                    "rules": payload["special_role_rules"]["rules"]
                    + (payload["special_role_rules"]["rules"][0].copy(),)
                }
            ),
            "特殊角色规则 code 必须唯一",
        ),
        (
            lambda payload: payload["teams"][1].update(
                {"strength_rank": payload["teams"][0]["strength_rank"]}
            ),
            "队伍强度排名必须唯一",
        ),
        (
            lambda payload: payload["strength_order_rules"].update(
                {
                    "orders": payload["strength_order_rules"]["orders"]
                    + (payload["strength_order_rules"]["orders"][0].copy(),)
                }
            ),
            "同一种强度指标只能配置一条顺序规则",
        ),
    ],
)
def test_definition_rejects_ambiguous_rule_identifiers(mutate, message: str) -> None:
    payload = builtin_raid_12_definition().model_dump()
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        type(builtin_raid_12_definition()).model_validate(payload)
