import json
from collections import Counter
from dataclasses import asdict, dataclass, replace

import pytest

from app.domain.dungeon import builtin_raid_12_definition
from app.schemas.dungeon import RoleType
from app.solver import (
    LockedAssignment,
    SolverAssignment,
    SolverInput,
    SolverParticipant,
    SolverPlayerPreference,
    SolverResult,
    SolverScheduleRule,
    SolverScheduleRuleType,
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
    max_damage_spread: int | None = None
    max_buffer_spread: int | None = None
    max_strength_order_violation_count: int | None = None
    unassigned_codes: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class QualityScenario:
    name: str
    solver_input: SolverInput
    expectation: QualityExpectation


DAMAGE_SCORES = (15_000, 14_000, 13_000, 12_000, 11_000, 10_000, 9_000, 8_000, 7_000)
BUFFER_SCORES = (60, 50, 40)
ANONYMIZED_PLAYER_PROFILES = (
    (7, 6),
    (8, 5),
    (8, 5),
    (8, 5),
    (8, 5),
    (8, 5),
    (9, 3),
    (9, 4),
    (9, 4),
    (10, 3),
    (11, 2),
)
ANONYMIZED_DAMAGE_BUCKETS = (
    17_000,
    12_000,
    9_000,
    7_700,
    6_500,
    5_250,
    4_500,
    3_700,
    3_000,
    2_500,
    1_500,
)
ANONYMIZED_BUFFER_BUCKETS = (535, 490, 472, 465, 458, 445, 427)


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


def _anonymized_profile_participants(
    profiles: tuple[tuple[int, int], ...],
) -> tuple[SolverParticipant, ...]:
    participants: list[SolverParticipant] = []
    for player_index, (damage_count, buffer_count) in enumerate(profiles):
        player_id = f"profile-player-{player_index:02d}"
        for role_index in range(damage_count):
            participants.append(
                SolverParticipant(
                    participant_id=f"profile-damage-{player_index:02d}-{role_index:02d}",
                    player_id=player_id,
                    role_type=RoleType.DAMAGE,
                    score=ANONYMIZED_DAMAGE_BUCKETS[
                        (player_index + role_index) % len(ANONYMIZED_DAMAGE_BUCKETS)
                    ],
                    is_treasure_damage=(
                        role_index == 0 or (player_index < 4 and role_index == 1)
                    ),
                )
            )
        fixed_buffer_count = 2 if player_index < 3 else 1 if player_index == 3 else 0
        for role_index in range(buffer_count):
            participants.append(
                SolverParticipant(
                    participant_id=f"profile-buffer-{player_index:02d}-{role_index:02d}",
                    player_id=player_id,
                    role_type=RoleType.BUFFER,
                    score=ANONYMIZED_BUFFER_BUCKETS[
                        (player_index + role_index) % len(ANONYMIZED_BUFFER_BUCKETS)
                    ],
                    allowed_team_keys=("RED",) if role_index < fixed_buffer_count else None,
                )
            )
    return tuple(participants)


def _anonymized_eleven_player_profile() -> QualityScenario:
    participants = _anonymized_profile_participants(ANONYMIZED_PLAYER_PROFILES)
    return QualityScenario(
        name="anonymized-eleven-player-profile",
        solver_input=_input(participants, time_limit_seconds=10),
        expectation=QualityExpectation(
            assigned_count=132,
            participant_count=142,
            complete_wave_count=0,
            complete_team_count=24,
            preferred_composition_count=24,
            special_rule_satisfied_count=0,
            damage_spread=0,
            buffer_spread=0,
            strength_order_violation_count=0,
            unassigned_codes={"UNASSIGNED_PLAYER_CONFLICT": 10},
            wave_fill=(11,) * 12,
        ),
    )


def _anonymized_twelve_player_complete_profile() -> QualityScenario:
    participants = _anonymized_profile_participants(
        (*ANONYMIZED_PLAYER_PROFILES, (9, 3))
    )
    return QualityScenario(
        name="anonymized-twelve-player-complete-profile",
        solver_input=_input(participants, time_limit_seconds=20),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=154,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=32,
            special_rule_satisfied_count=12,
            unassigned_codes={"UNASSIGNED_PLAYER_CONFLICT": 10},
            wave_fill=(12,) * 12,
        ),
    )


def _split_availability_complete_profile() -> QualityScenario:
    participants: list[SolverParticipant] = []
    for segment_index, allowed_waves in enumerate((tuple(range(1, 7)), tuple(range(7, 13)))):
        for player_index in range(12):
            role_type = RoleType.DAMAGE if player_index < 9 else RoleType.BUFFER
            for role_index in range(6):
                participants.append(
                    SolverParticipant(
                        participant_id=(
                            f"availability-{segment_index}-{player_index:02d}-{role_index:02d}"
                        ),
                        player_id=f"availability-player-{segment_index}-{player_index:02d}",
                        role_type=role_type,
                        score=(
                            6_000 + player_index * 250 + role_index * 50
                            if role_type == RoleType.DAMAGE
                            else 440 + player_index * 5 + role_index
                        ),
                        is_treasure_damage=role_type == RoleType.DAMAGE and player_index == 0,
                        allowed_waves=allowed_waves,
                        allowed_team_keys=(
                            ("RED",)
                            if role_type == RoleType.BUFFER and player_index == 9
                            else None
                        ),
                    )
                )
    return QualityScenario(
        name="split-availability-complete-profile",
        solver_input=_input(tuple(participants), time_limit_seconds=10),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=144,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=12,
            unassigned_codes={},
            wave_fill=(12,) * 12,
        ),
    )


def _fixed_lead_buffer_with_player_limits() -> QualityScenario:
    participants: list[SolverParticipant] = []
    preferences: list[SolverPlayerPreference] = []
    damage_scores = (28_000, 21_000, 15_500, 11_000, 7_500, 4_800, 2_900, 1_600)
    buffer_scores = (680, 590, 525, 470, 420, 365, 320, 275)

    for player_index in range(18):
        player_id = f"limited-damage-player-{player_index:02d}"
        preferences.append(SolverPlayerPreference(player_id, max_wave_count=6))
        for role_index, base_score in enumerate(damage_scores):
            participants.append(
                SolverParticipant(
                    participant_id=f"limited-damage-{player_index:02d}-{role_index:02d}",
                    player_id=player_id,
                    role_type=RoleType.DAMAGE,
                    score=base_score + player_index * 37,
                    is_treasure_damage=role_index == 0 and player_index < 12,
                )
            )

    for player_index in range(6):
        player_id = f"limited-buffer-player-{player_index:02d}"
        preferences.append(SolverPlayerPreference(player_id, max_wave_count=6))
        for role_index, base_score in enumerate(buffer_scores):
            participants.append(
                SolverParticipant(
                    participant_id=f"limited-buffer-{player_index:02d}-{role_index:02d}",
                    player_id=player_id,
                    role_type=RoleType.BUFFER,
                    score=base_score + player_index * 11,
                    allowed_team_keys=("RED",) if player_index < 2 else None,
                )
            )

    return QualityScenario(
        name="fixed-lead-buffer-with-player-limits",
        solver_input=replace(
            _input(tuple(participants), time_limit_seconds=20),
            player_preferences=tuple(preferences),
        ),
        expectation=QualityExpectation(
            assigned_count=144,
            participant_count=192,
            complete_wave_count=12,
            complete_team_count=36,
            preferred_composition_count=36,
            special_rule_satisfied_count=12,
            max_damage_spread=70_500,
            max_buffer_spread=710,
            max_strength_order_violation_count=13,
            unassigned_codes={"UNASSIGNED_PLAYER_CONFLICT": 48},
            wave_fill=(12,) * 12,
        ),
    )


def _natural_rule_with_player_limits() -> QualityScenario:
    base = _fixed_lead_buffer_with_player_limits()
    return QualityScenario(
        name="natural-rule-with-player-limits",
        solver_input=replace(
            base.solver_input,
            schedule_rules=(
                SolverScheduleRule(
                    rule_id="R1",
                    type=SolverScheduleRuleType.PLAYER_ALLOWED_WAVES,
                    explanation="指定 C 玩家只能参加前 6 波",
                    player_ids=("limited-damage-player-00",),
                    waves=tuple(range(1, 7)),
                ),
            ),
        ),
        expectation=base.expectation,
    )


SCENARIOS = (
    _balanced_complete(),
    _buffer_surplus_fallback(),
    _treasure_shortage(),
    _availability_shortage(),
    _same_player_conflicts(),
    _locked_core_assignments(),
    _late_concentrated_shortage(),
    _anonymized_eleven_player_profile(),
    _anonymized_twelve_player_complete_profile(),
    _split_availability_complete_profile(),
    _fixed_lead_buffer_with_player_limits(),
    _natural_rule_with_player_limits(),
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
    assignments_by_player: dict[str, list[SolverAssignment]] = {}
    for assignment in assignments:
        player_id = participants[assignment.participant_id].player_id
        assignments_by_player.setdefault(player_id, []).append(assignment)
    for rule in scenario.solver_input.schedule_rules:
        if rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES:
            assert all(
                assignment.wave_no in rule.waves
                for player_id in rule.player_ids
                for assignment in assignments_by_player.get(player_id, [])
            )
        elif rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES:
            assert all(
                assignment.wave_no not in rule.waves
                for player_id in rule.player_ids
                for assignment in assignments_by_player.get(player_id, [])
            )
        elif rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
            assert all(
                sum(
                    assignment.wave_no == wave_no
                    for player_id in rule.player_ids
                    for assignment in assignments_by_player.get(player_id, [])
                )
                <= 1
                for wave_no in range(1, scenario.solver_input.wave_count + 1)
            )
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE:
            required = assignment_by_participant[rule.participant_id or ""]
            assert required.wave_no == rule.waves[0]
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM:
            required = assignment_by_participant[rule.participant_id or ""]
            assert required.team_key == rule.team_key

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
                "objective_stages": [asdict(stage) for stage in result.objective_stages],
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
    if expectation.max_damage_spread is not None:
        assert summary.damage_spread <= expectation.max_damage_spread
    if expectation.max_buffer_spread is not None:
        assert summary.buffer_spread <= expectation.max_buffer_spread
    if expectation.max_strength_order_violation_count is not None:
        assert (
            summary.strength_order_violation_count
            <= expectation.max_strength_order_violation_count
        )
    if expectation.unassigned_codes is not None:
        assert Counter(item.code for item in result.unassigned) == expectation.unassigned_codes
    _assert_solver_invariants(scenario, result)
