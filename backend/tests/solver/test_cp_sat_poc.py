from collections import Counter, defaultdict

from app.schemas.dungeon import RoleType
from app.solver import SolverStatus, solve
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
