from datetime import UTC, datetime

import pytest

from app.db.seed import _validate_existing_builtin
from app.domain.dungeon import builtin_raid_12_definition
from app.models import Dungeon, DungeonTeamTemplate, DungeonVersion, FormulaVersion


def _existing_builtin() -> tuple[Dungeon, DungeonVersion]:
    definition = builtin_raid_12_definition()
    formula = FormulaVersion(
        code=definition.formula.code,
        version=definition.formula.version,
        config=definition.formula.model_dump(
            mode="json", by_alias=True, exclude={"code", "version"}
        ),
        is_active=True,
    )
    version = DungeonVersion(
        version_no=definition.version_no,
        status="PUBLISHED",
        default_wave_count=definition.default_wave_count,
        min_wave_count=definition.min_wave_count,
        max_wave_count=definition.max_wave_count,
        formula_version=formula,
        composition_rules=definition.composition_rules.model_dump(mode="json", by_alias=True),
        special_role_rules=definition.special_role_rules.model_dump(mode="json", by_alias=True),
        strength_order_rules=definition.strength_order_rules.model_dump(mode="json", by_alias=True),
        optimization_rules=definition.optimization_rules.model_dump(mode="json", by_alias=True),
        missing_slot_policy=definition.missing_slot_policy.model_dump(mode="json", by_alias=True),
        published_at=datetime.now(UTC),
    )
    version.teams = [
        DungeonTeamTemplate(
            team_key=team.team_key,
            display_name=team.display_name,
            display_color=team.display_color,
            display_order=team.display_order,
            member_count=team.member_count,
            strength_rank=team.strength_rank,
        )
        for team in definition.teams
    ]
    dungeon = Dungeon(code=definition.dungeon_code, name=definition.dungeon_name, is_active=True)
    dungeon.versions = [version]
    return dungeon, version


def test_existing_builtin_must_match_canonical_definition() -> None:
    dungeon, _version = _existing_builtin()
    definition = builtin_raid_12_definition()

    assert definition.version_no == 2
    assert definition.formula.buffer_scale == 100
    _validate_existing_builtin(dungeon, definition)


def test_existing_builtin_rejects_team_drift() -> None:
    dungeon, version = _existing_builtin()
    version.teams[0].member_count = 5

    with pytest.raises(RuntimeError, match="teams"):
        _validate_existing_builtin(dungeon, builtin_raid_12_definition())


def test_existing_builtin_rejects_missing_version() -> None:
    dungeon, _version = _existing_builtin()
    dungeon.versions = []

    with pytest.raises(RuntimeError, match="缺少 v2"):
        _validate_existing_builtin(dungeon, builtin_raid_12_definition())
