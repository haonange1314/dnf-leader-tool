from collections import Counter, defaultdict

import pytest

from app.schemas.dungeon import OptimizationRules, RoleType
from app.solver import SolverInput, SolverParticipant, SolverStatus, solve
from app.solver.fixtures import custom_party_4_input, default_raid_12_input


def test_default_12_wave_raid_is_complete_and_valid() -> None:
    solver_input = default_raid_12_input()
    result = solve(solver_input)

    assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert len(result.assignments) == 144
    assert result.unassigned_participant_ids == ()
    assert len({assignment.participant_id for assignment in result.assignments}) == 144
    assert Counter(a.wave_no for a in result.assignments) == {wave: 12 for wave in range(1, 13)}
    assert all(summary.member_count == 4 for summary in result.team_summaries)
    assert all(summary.composition_code == "3D1B" for summary in result.team_summaries)
    assert Counter(a.wave_no for a in result.special_assignments) == {
        wave: 1 for wave in range(1, 13)
    }
    assert all(a.team_key == "RED" for a in result.special_assignments)

    participants = {p.participant_id: p for p in solver_input.participants}
    players_by_wave: dict[int, list[str]] = defaultdict(list)
    for assignment in result.assignments:
        players_by_wave[assignment.wave_no].append(
            participants[assignment.participant_id].player_id
        )
    assert all(len(players) == len(set(players)) for players in players_by_wave.values())


def test_custom_single_team_four_person_dungeon() -> None:
    result = solve(custom_party_4_input())

    assert result.status == SolverStatus.OPTIMAL
    assert len(result.assignments) == 4
    assert {assignment.team_key for assignment in result.assignments} == {"PARTY"}
    assert result.team_summaries[0].role_counts == {
        RoleType.DAMAGE: 3,
        RoleType.BUFFER: 1,
    }
    assert result.special_assignments == ()


def test_same_player_is_never_assigned_twice_in_a_wave() -> None:
    solver_input = custom_party_4_input(include_player_conflict=True)
    result = solve(solver_input)
    participants = {p.participant_id: p for p in solver_input.participants}
    assigned_players = [participants[a.participant_id].player_id for a in result.assignments]

    assert len(result.assignments) == 4
    assert len(assigned_players) == len(set(assigned_players))


def test_empty_allowed_waves_means_participant_is_never_available() -> None:
    base_input = custom_party_4_input()
    unavailable = SolverParticipant(
        "unavailable",
        "player-unavailable",
        RoleType.DAMAGE,
        10_000,
        allowed_waves=(),
    )
    solver_input = SolverInput(
        dungeon=base_input.dungeon,
        wave_count=1,
        participants=(unavailable,),
        time_limit_seconds=1,
    )

    result = solve(solver_input)

    assert result.assignments == ()
    assert result.unassigned_participant_ids == ("unavailable",)


def test_complete_team_priority_cannot_be_overridden_by_balance_scores() -> None:
    base_definition = custom_party_4_input().dungeon
    balanced_definition = base_definition.model_copy(
        update={
            "optimization_rules": OptimizationRules(
                balance_across_waves=(RoleType.DAMAGE, RoleType.BUFFER)
            )
        }
    )
    participants = tuple(
        [
            SolverParticipant(
                f"damage-{index}", f"damage-player-{index}", RoleType.DAMAGE, 1_000_000
            )
            for index in range(4)
        ]
        + [
            SolverParticipant(
                f"buffer-{index}", f"buffer-player-{index}", RoleType.BUFFER, 1_000_000
            )
            for index in range(2)
        ]
    )

    result = solve(
        SolverInput(
            dungeon=balanced_definition,
            wave_count=2,
            participants=participants,
            time_limit_seconds=2,
        )
    )

    assert len(result.assignments) == 6
    assert sorted(summary.member_count for summary in result.team_summaries) == [2, 4]
    assert [
        summary.composition_code
        for summary in result.team_summaries
        if summary.composition_code is not None
    ] == ["3D1B"]


def test_solver_rejects_score_that_exceeds_int64_range() -> None:
    base_input = custom_party_4_input()
    participant = SolverParticipant("overflow", "player", RoleType.DAMAGE, 1 << 63)
    solver_input = SolverInput(
        dungeon=base_input.dungeon,
        wave_count=1,
        participants=(participant,),
        time_limit_seconds=1,
    )

    with pytest.raises(ValueError, match="64 位"):
        solve(solver_input)


def test_solver_rejects_wave_count_outside_dungeon_version_range() -> None:
    base_input = custom_party_4_input()
    solver_input = SolverInput(
        dungeon=base_input.dungeon,
        wave_count=13,
        participants=(),
        time_limit_seconds=1,
    )

    with pytest.raises(ValueError, match="副本版本允许范围"):
        solve(solver_input)
