from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.dungeon import CompositionRules, RoleType

MAX_WAVE_COUNT = 50
MAX_SCHEDULE_POSITIONS = 1_200


@dataclass(frozen=True)
class RoleRequirements:
    ideal_damage: int
    base_buffers: int


@dataclass(frozen=True)
class CompositionFeasibility:
    can_fill_all_teams: bool
    best_damage_usage: int | None
    best_buffer_usage: int | None
    minimum_damage: int
    maximum_damage: int
    minimum_buffers: int
    maximum_buffers: int
    closest_damage_required: int
    closest_buffers_required: int
    damage_shortage: int
    buffer_shortage: int


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


def composition_feasibility(
    composition_rules: CompositionRules,
    team_keys: Iterable[str],
    *,
    available_damage: int,
    available_buffers: int,
) -> CompositionFeasibility:
    """Check whether all teams can use an allowed full composition with the role pool."""
    reachable: set[tuple[int, int]] = {(0, 0)}
    for team_key in team_keys:
        options = {
            (
                rule.roles.get(RoleType.DAMAGE, 0),
                rule.roles.get(RoleType.BUFFER, 0),
            )
            for rule in composition_rules.allowed
            if team_key in rule.applicable_team_keys
        }
        if not options:
            raise ValueError(f"队伍 {team_key} 没有适用的组成规则")
        reachable = {
            (damage_used + option_damage, buffers_used + option_buffers)
            for damage_used, buffers_used in reachable
            for option_damage, option_buffers in options
        }

    feasible = [
        (damage_used, buffers_used)
        for damage_used, buffers_used in reachable
        if damage_used <= available_damage and buffers_used <= available_buffers
    ]
    best = max(feasible, default=None, key=lambda counts: (sum(counts), counts[0]))
    closest = min(
        reachable,
        key=lambda counts: (
            max(0, counts[0] - available_damage)
            + max(0, counts[1] - available_buffers),
            abs(counts[0] - available_damage) + abs(counts[1] - available_buffers),
        ),
    )
    return CompositionFeasibility(
        can_fill_all_teams=best is not None,
        best_damage_usage=best[0] if best is not None else None,
        best_buffer_usage=best[1] if best is not None else None,
        minimum_damage=min(damage for damage, _buffers in reachable),
        maximum_damage=max(damage for damage, _buffers in reachable),
        minimum_buffers=min(buffers for _damage, buffers in reachable),
        maximum_buffers=max(buffers for _damage, buffers in reachable),
        closest_damage_required=closest[0],
        closest_buffers_required=closest[1],
        damage_shortage=max(0, closest[0] - available_damage),
        buffer_shortage=max(0, closest[1] - available_buffers),
    )
