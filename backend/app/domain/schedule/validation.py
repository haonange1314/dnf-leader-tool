from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.dungeon import CompositionRules, RoleType

MAX_WAVE_COUNT = 50
MAX_SCHEDULE_POSITIONS = 1_200


@dataclass(frozen=True)
class RoleRequirements:
    ideal_damage: int
    base_buffers: int


def composition_role_requirements(
    composition_rules: CompositionRules, team_keys: Iterable[str]
) -> RoleRequirements:
    """Calculate safe shortage thresholds from a dungeon version's composition rules."""
    ideal_damage = 0
    base_buffers = 0
    for team_key in team_keys:
        applicable = [
            rule
            for rule in composition_rules.allowed
            if team_key in rule.applicable_team_keys
        ]
        if not applicable:
            raise ValueError(f"队伍 {team_key} 没有适用的组成规则")

        best_priority = min(rule.priority for rule in applicable)
        preferred = [rule for rule in applicable if rule.priority == best_priority]
        ideal_damage += min(rule.roles.get(RoleType.DAMAGE, 0) for rule in preferred)
        base_buffers += min(rule.roles.get(RoleType.BUFFER, 0) for rule in applicable)

    return RoleRequirements(ideal_damage=ideal_damage, base_buffers=base_buffers)
