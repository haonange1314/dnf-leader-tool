from collections import Counter

from app.domain.dungeon import builtin_raid_12_definition, custom_party_4_definition
from app.schemas.dungeon import RoleType
from app.solver import (
    LockedAssignment,
    SolverInput,
    SolverParticipant,
    SolverPlayerPreference,
    SolverStatus,
    solve,
)


def test_fallback_composition_fills_builtin_raid_with_two_damage_two_buffers() -> None:
    participants = tuple(
        [
            SolverParticipant(f"d-{index}", f"dp-{index}", RoleType.DAMAGE, 10_000)
            for index in range(6)
        ]
        + [
            SolverParticipant(f"b-{index}", f"bp-{index}", RoleType.BUFFER, 50)
            for index in range(6)
        ]
    )

    result = solve(
        SolverInput(
            dungeon=builtin_raid_12_definition(),
            wave_count=1,
            participants=participants,
            time_limit_seconds=2,
        )
    )

    assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert {summary.composition_code for summary in result.team_summaries} == {"2D2B"}
    assert result.objective_summary.complete_wave_count == 1
    assert result.objective_summary.preferred_composition_count == 0


def test_missing_slots_are_concentrated_in_later_waves() -> None:
    participants = tuple(
        [
            SolverParticipant(f"d-{index}", f"dp-{index}", RoleType.DAMAGE, 10_000)
            for index in range(4)
        ]
        + [SolverParticipant("b-0", "bp-0", RoleType.BUFFER, 50)]
    )

    result = solve(
        SolverInput(
            dungeon=custom_party_4_definition(),
            wave_count=2,
            participants=participants,
            time_limit_seconds=2,
        )
    )

    counts = Counter(assignment.wave_no for assignment in result.assignments)
    assert counts[1] == 4
    assert counts[2] == 1
    assert result.status == SolverStatus.PARTIAL


def test_locked_assignment_and_player_max_wave_count_are_preserved() -> None:
    participants = (
        SolverParticipant("d-locked", "player-a", RoleType.DAMAGE, 11_000),
        SolverParticipant("d-alt", "player-a", RoleType.DAMAGE, 12_000),
        SolverParticipant("d-2", "player-b", RoleType.DAMAGE, 10_000),
        SolverParticipant("d-3", "player-c", RoleType.DAMAGE, 9_000),
        SolverParticipant("b-1", "player-d", RoleType.BUFFER, 50),
    )

    result = solve(
        SolverInput(
            dungeon=custom_party_4_definition(),
            wave_count=2,
            participants=participants,
            player_preferences=(SolverPlayerPreference("player-a", max_wave_count=1),),
            locked_assignments=(LockedAssignment("d-locked", 2, "PARTY"),),
            time_limit_seconds=2,
        )
    )

    locked = next(item for item in result.assignments if item.participant_id == "d-locked")
    assert (locked.wave_no, locked.team_key) == (2, "PARTY")
    assert sum(item.participant_id in {"d-locked", "d-alt"} for item in result.assignments) == 1
    assert (
        next(reason for reason in result.unassigned if reason.participant_id == "d-alt").code
        == "UNASSIGNED_PLAYER_CONFLICT"
    )


def test_unavailable_participant_has_actionable_diagnostic() -> None:
    result = solve(
        SolverInput(
            dungeon=custom_party_4_definition(),
            wave_count=1,
            participants=(
                SolverParticipant(
                    "unavailable",
                    "player",
                    RoleType.DAMAGE,
                    10_000,
                    allowed_waves=(),
                ),
            ),
            time_limit_seconds=1,
        )
    )

    assert result.status == SolverStatus.PARTIAL
    assert result.unassigned[0].code == "UNASSIGNED_NO_AVAILABLE_WAVE"
