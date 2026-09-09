import uuid

import pytest
from pydantic import ValidationError

from app.domain.dungeon import builtin_raid_12_definition
from app.domain.schedule import (
    composition_feasibility,
    composition_role_requirements,
    distinct_player_feasibility,
    ordered_buffer_limits,
)
from app.schemas.dungeon import CompositionRule, CompositionRules, RoleType
from app.schemas.schedule import (
    PlayerPreferenceInput,
    ScheduleCopy,
    ScheduleCreate,
    ScheduleParticipantsUpdate,
    ScheduleUpdate,
)


def test_builtin_raid_role_requirements_follow_composition_priorities() -> None:
    definition = builtin_raid_12_definition()
    team_keys = [team.team_key for team in definition.teams] * definition.default_wave_count

    requirements = composition_role_requirements(definition.composition_rules, team_keys)

    assert requirements.ideal_damage == 117
    assert requirements.base_buffers == 39


def test_builtin_ordered_buffer_range_stops_before_green_double_buffer() -> None:
    definition = builtin_raid_12_definition()
    placement = definition.optimization_rules.buffer_placement
    assert placement is not None
    team_keys = [team.team_key for team in definition.teams] * 13

    minimum, maximum = ordered_buffer_limits(
        definition.composition_rules,
        team_keys,
        placement.double_buffer_team_keys,
    )

    assert (minimum, maximum) == (39, 65)


def test_custom_damage_only_composition_does_not_require_a_buffer() -> None:
    rules = CompositionRules(
        allowed=(
            CompositionRule(
                code="4D",
                applicable_team_keys=("PARTY",),
                roles={RoleType.DAMAGE: 4},
                priority=1,
            ),
        )
    )

    requirements = composition_role_requirements(rules, ["PARTY"])

    assert requirements.ideal_damage == 4
    assert requirements.base_buffers == 0


def test_custom_two_damage_two_buffer_composition_uses_two_buffer_baseline() -> None:
    rules = CompositionRules(
        allowed=(
            CompositionRule(
                code="2D2B",
                applicable_team_keys=("PARTY",),
                roles={RoleType.DAMAGE: 2, RoleType.BUFFER: 2},
                priority=1,
            ),
        )
    )

    requirements = composition_role_requirements(rules, ["PARTY"])

    assert requirements.ideal_damage == 2
    assert requirements.base_buffers == 2


def test_builtin_fallback_composition_can_fill_with_six_damage_and_six_buffers() -> None:
    definition = builtin_raid_12_definition()

    result = composition_feasibility(
        definition.composition_rules,
        (team.team_key for team in definition.teams),
        available_damage=6,
        available_buffers=6,
    )

    assert result.can_fill_all_teams is True
    assert result.best_damage_usage == 6
    assert result.best_buffer_usage == 6
    assert result.maximum_damage == 9


def test_builtin_full_composition_reports_role_infeasibility() -> None:
    definition = builtin_raid_12_definition()

    result = composition_feasibility(
        definition.composition_rules,
        (team.team_key for team in definition.teams),
        available_damage=5,
        available_buffers=7,
    )

    assert result.can_fill_all_teams is False
    assert result.minimum_damage == 6


def test_distinct_player_shortage_ignores_extra_characters_from_same_player() -> None:
    result = distinct_player_feasibility(
        12,
        [*(f"player-{index}" for index in range(11)), "player-0", "player-0"],
    )

    assert result.current == 11
    assert result.shortage == 1
    assert result.can_fill_wave is False


def test_custom_four_player_dungeon_can_fill_with_four_distinct_players() -> None:
    result = distinct_player_feasibility(4, ["a", "b", "c", "d"])

    assert result.shortage == 0
    assert result.can_fill_wave is True


def test_schedule_name_rejects_whitespace_only_input() -> None:
    with pytest.raises(ValidationError, match="排表名称不能为空"):
        ScheduleCreate(name="   ", dungeon_version_id=uuid.uuid4())


def test_schedule_name_is_trimmed_before_persistence() -> None:
    payload = ScheduleCreate(name="  周六团  ", dungeon_version_id=uuid.uuid4())

    assert payload.name == "周六团"


def test_schedule_update_requires_a_business_change() -> None:
    with pytest.raises(ValidationError, match="至少修改"):
        ScheduleUpdate(base_revision=1)


def test_schedule_damage_balance_tolerance_defaults_to_twenty_percent() -> None:
    payload = ScheduleCreate(name="周六团", dungeon_version_id=uuid.uuid4())

    assert payload.damage_balance_tolerance_percent == 20


@pytest.mark.parametrize("value", [-1, 101])
def test_schedule_damage_balance_tolerance_stays_in_supported_range(value: int) -> None:
    with pytest.raises(ValidationError):
        ScheduleUpdate(base_revision=1, damage_balance_tolerance_percent=value)


def test_schedule_copy_name_is_trimmed() -> None:
    payload = ScheduleCopy(base_revision=1, name="  周六团 - 副本  ")

    assert payload.name == "周六团 - 副本"


def test_schedule_participant_selection_rejects_duplicate_ids() -> None:
    participant_id = uuid.uuid4()

    with pytest.raises(ValidationError, match="不能重复"):
        ScheduleParticipantsUpdate(
            base_revision=1,
            selected_participant_ids=[participant_id, participant_id],
        )


def test_player_preference_sorts_allowed_waves() -> None:
    preference = PlayerPreferenceInput(
        player_id=uuid.uuid4(),
        allowed_waves=[3, 1, 2],
    )

    assert preference.allowed_waves == [1, 2, 3]
