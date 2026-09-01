import json
from collections import Counter
from dataclasses import asdict, dataclass, replace

import pytest

from app.domain.dungeon import builtin_raid_12_definition
from app.schemas.dungeon import RoleType
from app.solver import (
    LockedAssignment,
    SolverInput,
    SolverParticipant,
    SolverResult,
    SolverStatus,
    solve,
)


@dataclass(frozen=True, slots=True)
class QualityExpectation:
    assigned_count: int
    complete_wave_count: int
    complete_team_count: int
    preferred_composition_count: int
    special_rule_satisfied_count: int
    wave_fill: tuple[int, ...]
    participant_count: int | None = None
    damage_spread: int | None = None
    buffer_spread: int | None = None
    strength_order_violation_count: int | None = None
    unassigned_codes: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class QualityScenario:
    name: str
    solver_input: SolverInput
    expectation: QualityExpectation


DAMAGE_SCORES = (15_000, 14_000, 13_000, 12_000, 11_000, 10_000, 9_000, 8_000, 7_000)
BUFFER_SCORES = (60, 50, 40)


def _fixed_wave_participants(
    *,
    damage_scores: tuple[int, ...] = DAMAGE_SCORES,
    buffer_scores: tuple[int, ...] = BUFFER_SCORES,
    treasure_waves: frozenset[int] = frozenset(range(1, 13)),
) -> tuple[SolverParticipant, ...]:
    participants: list[SolverParticipant] = []
    for wave_no in range(1, 13):
        for index, score in enumerate(damage_scores):
            participants.append(
                SolverParticipant(
                    participant_id=f"damage-{wave_no:02d}-{index:02d}",
                    player_id=f"damage-player-{wave_no:02d}-{index:02d}",
                    role_type=RoleType.DAMAGE,
                    score=score,
                    is_treasure_damage=index == 0 and wave_no in treasure_waves,
                    allowed_waves=(wave_no,),
                )
            )
        for index, score in enumerate(buffer_scores):
            participants.append(
                SolverParticipant(
                    participant_id=f"buffer-{wave_no:02d}-{index:02d}",
                    player_id=f"buffer-player-{wave_no:02d}-{index:02d}",
                    role_type=RoleType.BUFFER,
                    score=score,
                    allowed_waves=(wave_no,),
                )
            )
    return tuple(participants)


def _input(
    participants: tuple[SolverParticipant, ...],
    *,
    locked_assignments: tuple[LockedAssignment, ...] = (),
    time_limit_seconds: float = 5,
) -> SolverInput:
    return SolverInput(
        dungeon=builtin_raid_12_definition(),
        wave_count=12,
        participants=participants,
        locked_assignments=locked_assignments,
        random_seed=42,
        time_limit_seconds=time_limit_seconds,
    )


def _balanced_complete() -> QualityScenario:
    return QualityScenario(
        name="balanced-complete",
        solver_input=_input(_fixed_wave_participants()),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=144,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=12,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            wave_fill=(12,) * 12,
        ),
    )


def _buffer_surplus_fallback() -> QualityScenario:
    participants = _fixed_wave_participants(
        damage_scores=DAMAGE_SCORES[:6],
        buffer_scores=(60, 55, 50, 45, 40, 35),
    )
    return QualityScenario(
        name="buffer-surplus-fallback",
        solver_input=_input(participants),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=144,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=0,
            special_rule_satisfied_count=12,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            wave_fill=(12,) * 12,
        ),
    )


def _treasure_shortage() -> QualityScenario:
    return QualityScenario(
        name="treasure-shortage",
        solver_input=_input(
            _fixed_wave_participants(treasure_waves=frozenset(range(1, 7)))
        ),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=144,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=6,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            wave_fill=(12,) * 12,
        ),
    )


def _availability_shortage() -> QualityScenario:
    unavailable_id = "damage-12-08"
    participants = tuple(
        replace(participant, allowed_waves=())
        if participant.participant_id == unavailable_id
        else participant
        for participant in _fixed_wave_participants()
    )
    return QualityScenario(
        name="availability-shortage",
        solver_input=_input(participants),
        expectation=QualityExpectation(
            assigned_count=143,
            participant_count=144,
            complete_wave_count=11,
            complete_team_count=35,
            preferred_composition_count=35,
            special_rule_satisfied_count=11,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            unassigned_codes={"UNASSIGNED_NO_AVAILABLE_WAVE": 1},
            wave_fill=(12,) * 11 + (11,),
        ),
    )


def _same_player_conflicts() -> QualityScenario:
    base = _fixed_wave_participants()
    alternatives = tuple(
        SolverParticipant(
            participant_id=f"damage-alt-{wave_no:02d}",
            player_id=f"damage-player-{wave_no:02d}-08",
            role_type=RoleType.DAMAGE,
            score=7_500,
            allowed_waves=(wave_no,),
        )
        for wave_no in range(1, 13)
    )
    return QualityScenario(
        name="same-player-conflicts",
        solver_input=_input(base + alternatives),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=156,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=12,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            unassigned_codes={"UNASSIGNED_PLAYER_CONFLICT": 12},
            wave_fill=(12,) * 12,
        ),
    )


def _locked_core_assignments() -> QualityScenario:
    locks = tuple(
        LockedAssignment(
            participant_id=f"damage-{wave_no:02d}-00",
            wave_no=wave_no,
            team_key="RED",
        )
        for wave_no in range(1, 13)
    )
    return QualityScenario(
        name="locked-core-assignments",
        solver_input=_input(_fixed_wave_participants(), locked_assignments=locks),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=144,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=12,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            wave_fill=(12,) * 12,
        ),
    )


def _late_concentrated_shortage() -> QualityScenario:
    participants = tuple(
        [
            SolverParticipant(
                participant_id=f"damage-flex-{index:03d}",
                player_id=f"damage-flex-player-{index:03d}",
                role_type=RoleType.DAMAGE,
                score=9_000 + (index % 24) * 75,
                is_treasure_damage=index < 12,
            )
            for index in range(102)
        ]
        + [
            SolverParticipant(
                participant_id=f"buffer-flex-{index:03d}",
                player_id=f"buffer-flex-player-{index:03d}",
                role_type=RoleType.BUFFER,
                score=35 + (index % 12),
            )
            for index in range(34)
        ]
    )
    return QualityScenario(
        name="late-concentrated-shortage",
        solver_input=_input(participants, time_limit_seconds=10),
        expectation=QualityExpectation(
            assigned_count=136,
            participant_count=136,
            complete_wave_count=11,
            complete_team_count=34,
            preferred_composition_count=34,
            special_rule_satisfied_count=11,
            wave_fill=(12,) * 11 + (4,),
        ),
    )


SCENARIOS = (
    _balanced_complete(),
    _buffer_surplus_fallback(),
    _treasure_shortage(),
    _availability_shortage(),
    _same_player_conflicts(),
    _locked_core_assignments(),
    _late_concentrated_shortage(),
)


def _assert_solver_invariants(scenario: QualityScenario, result: SolverResult) -> None:
    assignments = result.assignments
    participants = {item.participant_id: item for item in scenario.solver_input.participants}
    assignment_by_participant = {item.participant_id: item for item in assignments}
    assert len(assignments) == len({item.participant_id for item in assignments})
    assert all(item.participant_id in participants for item in assignments)
    assert result.objective_summary.assigned_count == len(assignments)
    assert not set(result.unassigned_participant_ids) & assignment_by_participant.keys()

    player_waves = [
        (participants[item.participant_id].player_id, item.wave_no) for item in assignments
    ]
    assert len(player_waves) == len(set(player_waves))

    team_capacity = {
        team.team_key: team.member_count for team in scenario.solver_input.dungeon.teams
    }
    assigned_by_team = Counter((item.wave_no, item.team_key) for item in assignments)
    assert all(
        count <= team_capacity[team_key]
        for (_wave_no, team_key), count in assigned_by_team.items()
    )
    for locked in scenario.solver_input.locked_assignments:
        assignment = assignment_by_participant[locked.participant_id]
        assert (assignment.wave_no, assignment.team_key) == (locked.wave_no, locked.team_key)
    for special in result.special_assignments:
        participant = participants[special.participant_id]
        assignment = assignment_by_participant[special.participant_id]
        assert participant.role_type == RoleType.DAMAGE
        assert participant.is_treasure_damage
        assert (assignment.wave_no, assignment.team_key) == (
            special.wave_no,
            special.team_key,
        )


@pytest.mark.quality
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_raid_quality_baseline(scenario: QualityScenario) -> None:
    result = solve(scenario.solver_input)
    summary = result.objective_summary
    expectation = scenario.expectation
    wave_fill_counter = Counter(item.wave_no for item in result.assignments)
    wave_fill = tuple(wave_fill_counter[wave_no] for wave_no in range(1, 13))

    print(
        json.dumps(
            {
                "scenario": scenario.name,
                "status": result.status.value,
                **asdict(summary),
                "wave_fill": wave_fill,
                "unassigned_codes": dict(Counter(item.code for item in result.unassigned)),
                "wall_time_seconds": round(result.wall_time_seconds, 3),
            },
            ensure_ascii=False,
        )
    )

    assert result.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE, SolverStatus.PARTIAL}
    assert summary.assigned_count == expectation.assigned_count
    expected_participant_count = (
        expectation.participant_count
        if expectation.participant_count is not None
        else len(scenario.solver_input.participants)
    )
    assert summary.participant_count == expected_participant_count
    assert summary.complete_wave_count == expectation.complete_wave_count
    assert summary.complete_team_count == expectation.complete_team_count
    assert summary.preferred_composition_count == expectation.preferred_composition_count
    assert summary.special_rule_satisfied_count == expectation.special_rule_satisfied_count
    assert wave_fill == expectation.wave_fill
    if expectation.damage_spread is not None:
        assert summary.damage_spread == expectation.damage_spread
    if expectation.buffer_spread is not None:
        assert summary.buffer_spread == expectation.buffer_spread
    if expectation.strength_order_violation_count is not None:
        assert (
            summary.strength_order_violation_count
            == expectation.strength_order_violation_count
        )
    if expectation.unassigned_codes is not None:
        assert Counter(item.code for item in result.unassigned) == expectation.unassigned_codes
    _assert_solver_invariants(scenario, result)
