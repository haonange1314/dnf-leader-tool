from app.solver import solve
from app.solver.fixtures import custom_party_4_input, default_raid_12_input


def main() -> None:
    scenarios = (
        ("default-12-wave-raid", default_raid_12_input()),
        ("custom-single-party-4", custom_party_4_input()),
    )
    for name, scenario in scenarios:
        result = solve(scenario)
        assignment_summary = (
            f"assigned={len(result.assignments)} "
            f"unassigned={len(result.unassigned_participant_ids)}"
        )
        print(
            f"{name}: status={result.status.value} "
            f"{assignment_summary} seconds={result.wall_time_seconds:.3f}"
        )


if __name__ == "__main__":
    main()
