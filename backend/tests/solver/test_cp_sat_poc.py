from collections import Counter, defaultdict

import pytest
from ortools.sat.python import cp_model

import app.solver.cp_sat as cp_sat_module
from app.schemas.dungeon import MissingSlotPolicy, OptimizationRules, RoleType
from app.solver import (
    ObjectiveStageOutcome,
    SolverInput,
    SolverParticipant,
    SolverStatus,
    solve,
)
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
    stage_codes = [stage.code for stage in result.objective_stages]
    assert stage_codes.index("BALANCE_DAMAGE") < stage_codes.index("BALANCE_BUFFER")
    assert all(stage.duration_seconds >= 0 for stage in result.objective_stages)
    stage_by_code = {stage.code: stage for stage in result.objective_stages}
    assert stage_by_code["BALANCE_DAMAGE"].value == result.objective_summary.damage_spread
    assert stage_by_code["BALANCE_BUFFER"].value == result.objective_summary.buffer_spread
    if any(
        stage.outcome == ObjectiveStageOutcome.FEASIBLE
        for stage in result.objective_stages
    ):
        assert result.status == SolverStatus.FEASIBLE

    participants = {p.participant_id: p for p in solver_input.participants}
    players_by_wave: dict[int, list[str]] = defaultdict(list)
    for assignment in result.assignments:
        players_by_wave[assignment.wave_no].append(
            participants[assignment.participant_id].player_id
        )
    assert all(len(players) == len(set(players)) for players in players_by_wave.values())


def test_late_stage_timeout_keeps_incumbent_and_records_remaining_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_solve_stage = cp_sat_module._solve_stage
    call_count = 0

    def timeout_after_early_fill(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 4:
            timed_out_solver = cp_model.CpSolver()
            timed_out_solver.solve(cp_model.CpModel())
            return timed_out_solver, SolverStatus.ERROR
        return original_solve_stage(*args, **kwargs)

    monkeypatch.setattr(cp_sat_module, "_solve_stage", timeout_after_early_fill)

    result = cp_sat_module.solve(default_raid_12_input())

    stage_by_code = {stage.code: stage for stage in result.objective_stages}
    assert {
        "COMPOSITION_PRIORITY",
        "SPECIAL_ROLE",
        "STRENGTH_ORDER",
        "BALANCE_DAMAGE",
        "BALANCE_BUFFER",
        "SPECIAL_COMPANION",
    } <= stage_by_code.keys()
    assert result.status == SolverStatus.FEASIBLE
    assert stage_by_code["BALANCE_DAMAGE"].value == result.objective_summary.damage_spread
    assert stage_by_code["BALANCE_BUFFER"].value == result.objective_summary.buffer_spread


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


def test_participant_can_be_restricted_to_definition_team_keys() -> None:
    definition = default_raid_12_input().dungeon
    participants = tuple(
        [
            SolverParticipant(
                f"damage-{index}", f"damage-player-{index}", RoleType.DAMAGE, 1000
            )
            for index in range(3)
        ]
        + [
            SolverParticipant(
                "fixed-buffer",
                "buffer-player",
                RoleType.BUFFER,
                500,
                allowed_team_keys=("RED",),
            )
        ]
    )

    result = solve(
        SolverInput(
            dungeon=definition,
            wave_count=1,
            participants=participants,
            time_limit_seconds=1,
        )
    )

    fixed_assignment = next(
        assignment
        for assignment in result.assignments
        if assignment.participant_id == "fixed-buffer"
    )
    assert fixed_assignment.team_key == "RED"


def test_player_upper_bound_search_falls_back_when_team_capacity_is_tighter() -> None:
    definition = default_raid_12_input().dungeon
    participants = (
        SolverParticipant(
            "damage-0", "player-0", RoleType.DAMAGE, 1000, allowed_team_keys=("RED",)
        ),
        SolverParticipant(
            "damage-1", "player-1", RoleType.DAMAGE, 900, allowed_team_keys=("RED",)
        ),
        SolverParticipant(
            "damage-2", "player-2", RoleType.DAMAGE, 800, allowed_team_keys=("RED",)
        ),
        SolverParticipant(
            "buffer-0", "player-3", RoleType.BUFFER, 500, allowed_team_keys=("RED",)
        ),
        SolverParticipant(
            "damage-3", "player-4", RoleType.DAMAGE, 700, allowed_team_keys=("RED",)
        ),
        SolverParticipant(
            "buffer-1", "player-4", RoleType.BUFFER, 400, allowed_team_keys=("RED",)
        ),
    )

    result = solve(
        SolverInput(
            dungeon=definition,
            wave_count=1,
            participants=participants,
            time_limit_seconds=5,
        )
    )

    assert len(result.assignments) == 4
    assert result.objective_summary.complete_team_count == 1


def test_dense_player_hint_uses_reachable_assignment_bound() -> None:
    definition = default_raid_12_input().dungeon
    participants = tuple(
        SolverParticipant(
            participant_id=f"player-{player_index}-role-{role_index}",
            player_id=f"player-{player_index}",
            role_type=(RoleType.DAMAGE if player_index < 9 else RoleType.BUFFER),
            score=1000 + role_index,
            allowed_team_keys=None if player_index < 9 else ("RED",),
        )
        for player_index in range(12)
        for role_index in range(2)
    )

    solver_input = SolverInput(
        dungeon=definition,
        wave_count=2,
        participants=participants,
        time_limit_seconds=5,
    )
    result = solve(solver_input)
    repeated_result = solve(solver_input)

    # The generic player/position bound is 24, but buffers restricted to RED make
    # only 10 assignments per wave reachable: RED 2D2B plus two partial 3D teams.
    assert result.objective_summary.assigned_count == 20
    assert Counter(assignment.wave_no for assignment in result.assignments) == {1: 10, 2: 10}
    assert repeated_result.assignments == result.assignments


def test_failed_hint_time_is_included_in_error_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solver_input = custom_party_4_input(include_player_conflict=True)

    monkeypatch.setattr(
        cp_sat_module,
        "_find_assignment_target_hint",
        lambda *_args, **_kwargs: (None, 0.4, 0),
    )

    def fail_stage(*_args, **_kwargs):
        failed_solver = cp_model.CpSolver()
        failed_solver.solve(cp_model.CpModel())
        return failed_solver, SolverStatus.ERROR

    monkeypatch.setattr(cp_sat_module, "_solve_stage", fail_stage)

    result = cp_sat_module.solve(solver_input)

    assert result.status == SolverStatus.ERROR
    assert result.wall_time_seconds >= 0.4


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


def test_spread_evenly_balances_missing_slots_across_waves() -> None:
    base_definition = custom_party_4_input().dungeon
    spread_definition = base_definition.model_copy(
        update={"missing_slot_policy": MissingSlotPolicy(mode="SPREAD_EVENLY")}
    )
    participants = tuple(
        [
            SolverParticipant(
                f"damage-{index}", f"damage-player-{index}", RoleType.DAMAGE, 1_000
            )
            for index in range(4)
        ]
        + [
            SolverParticipant(
                f"buffer-{index}", f"buffer-player-{index}", RoleType.BUFFER, 1_000
            )
            for index in range(2)
        ]
    )

    result = solve(
        SolverInput(
            dungeon=spread_definition,
            wave_count=2,
            participants=participants,
            time_limit_seconds=2,
        )
    )

    assert Counter(assignment.wave_no for assignment in result.assignments) == {1: 3, 2: 3}


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
