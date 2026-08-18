from app.domain.dungeon import builtin_raid_12_definition, custom_party_4_definition
from app.schemas.dungeon import RoleType
from app.solver.models import SolverInput, SolverParticipant


def default_raid_12_input(*, time_limit_seconds: float = 10.0) -> SolverInput:
    participants: list[SolverParticipant] = []
    for index in range(108):
        participants.append(
            SolverParticipant(
                participant_id=f"damage-{index:03d}",
                player_id=f"damage-player-{index:03d}",
                role_type=RoleType.DAMAGE,
                score=9_000 + (index % 24) * 75,
                is_treasure_damage=index < 12,
            )
        )
    for index in range(36):
        participants.append(
            SolverParticipant(
                participant_id=f"buffer-{index:03d}",
                player_id=f"buffer-player-{index:03d}",
                role_type=RoleType.BUFFER,
                score=35 + (index % 12),
            )
        )
    return SolverInput(
        dungeon=builtin_raid_12_definition(),
        wave_count=12,
        participants=tuple(participants),
        time_limit_seconds=time_limit_seconds,
    )


def custom_party_4_input(*, include_player_conflict: bool = False) -> SolverInput:
    participants = [
        SolverParticipant("damage-a", "player-a", RoleType.DAMAGE, 12_000),
        SolverParticipant("damage-b", "player-b", RoleType.DAMAGE, 11_000),
        SolverParticipant("damage-c", "player-c", RoleType.DAMAGE, 10_000),
        SolverParticipant("buffer-a", "player-d", RoleType.BUFFER, 45),
    ]
    if include_player_conflict:
        participants.append(SolverParticipant("damage-a-alt", "player-a", RoleType.DAMAGE, 13_000))
    return SolverInput(
        dungeon=custom_party_4_definition(),
        wave_count=1,
        participants=tuple(participants),
        time_limit_seconds=3,
    )
