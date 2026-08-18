import uuid

import pytest
from pydantic import ValidationError

from app.domain.dungeon import builtin_raid_12_definition
from app.domain.schedule import composition_role_requirements
from app.schemas.dungeon import CompositionRule, CompositionRules, RoleType
from app.schemas.schedule import ScheduleCreate


def test_builtin_raid_role_requirements_follow_composition_priorities() -> None:
    definition = builtin_raid_12_definition()
    team_keys = [team.team_key for team in definition.teams] * definition.default_wave_count

    requirements = composition_role_requirements(definition.composition_rules, team_keys)

    assert requirements.ideal_damage == 108
    assert requirements.base_buffers == 36


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


def test_schedule_name_rejects_whitespace_only_input() -> None:
    with pytest.raises(ValidationError, match="排表名称不能为空"):
        ScheduleCreate(name="   ", dungeon_version_id=uuid.uuid4())


def test_schedule_name_is_trimmed_before_persistence() -> None:
    payload = ScheduleCreate(name="  周六团  ", dungeon_version_id=uuid.uuid4())

    assert payload.name == "周六团"
