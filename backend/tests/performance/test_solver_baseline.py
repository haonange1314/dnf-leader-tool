import json

import pytest

from app.domain.dungeon import builtin_raid_12_definition
from app.schemas.dungeon import RoleType
from app.solver import SolverInput, SolverParticipant, SolverStatus, solve


def raid_input(wave_count: int, time_limit_seconds: float) -> SolverInput:
    damage_count = wave_count * 9
    buffer_count = wave_count * 3
    constrain_to_target_wave = wave_count > 12
    participants = tuple(
        [
            SolverParticipant(
                participant_id=f"damage-{index:04d}",
                player_id=f"damage-player-{index:04d}",
                role_type=RoleType.DAMAGE,
                score=9_000 + (index % 48) * 50,
                is_treasure_damage=(
                    index % 9 == 0 if constrain_to_target_wave else index < wave_count
                ),
                allowed_waves=(index // 9 + 1,) if constrain_to_target_wave else None,
            )
            for index in range(damage_count)
        ]
        + [
            SolverParticipant(
                participant_id=f"buffer-{index:04d}",
                player_id=f"buffer-player-{index:04d}",
                role_type=RoleType.BUFFER,
                score=35 + (index % 16),
                allowed_waves=(index // 3 + 1,) if constrain_to_target_wave else None,
            )
            for index in range(buffer_count)
        ]
    )
    return SolverInput(
        dungeon=builtin_raid_12_definition(),
        wave_count=wave_count,
        participants=participants,
        time_limit_seconds=time_limit_seconds,
    )


@pytest.mark.performance
@pytest.mark.parametrize(
    ("wave_count", "time_limit_seconds"),
    [(1, 2.0), (12, 5.0), (30, 8.0), (50, 12.0)],
)
def test_builtin_raid_solver_performance_baseline(
    wave_count: int, time_limit_seconds: float
) -> None:
    solver_input = raid_input(wave_count, time_limit_seconds)
    result = solve(solver_input)

    print(
        json.dumps(
            {
                "waveCount": wave_count,
                "participants": len(solver_input.participants),
                "status": result.status.value,
                "assigned": len(result.assignments),
                "wallTimeSeconds": round(result.wall_time_seconds, 3),
                "timeLimitSeconds": time_limit_seconds,
                "profile": "wave-constrained" if wave_count > 12 else "fully-flexible",
            },
            ensure_ascii=False,
        )
    )
    if wave_count <= 12:
        assert result.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}
        assert len(result.assignments) == wave_count * 12
        assert result.objective_summary.complete_wave_count == wave_count
    else:
        # Oversized layouts must return a useful bounded result instead of hanging.
        assert result.status in {
            SolverStatus.OPTIMAL,
            SolverStatus.FEASIBLE,
            SolverStatus.PARTIAL,
        }
        assert len(result.assignments) >= wave_count * 12 * 0.70
    assert result.wall_time_seconds <= time_limit_seconds + 1
