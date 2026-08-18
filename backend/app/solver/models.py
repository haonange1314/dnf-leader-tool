from dataclasses import dataclass
from enum import StrEnum

from app.schemas.dungeon import DungeonVersionDefinition, RoleType


class SolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class SolverParticipant:
    participant_id: str
    player_id: str
    role_type: RoleType
    score: int
    is_treasure_damage: bool = False
    allowed_waves: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class SolverInput:
    dungeon: DungeonVersionDefinition
    wave_count: int
    participants: tuple[SolverParticipant, ...]
    random_seed: int = 42
    time_limit_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class SolverAssignment:
    participant_id: str
    wave_no: int
    team_key: str


@dataclass(frozen=True, slots=True)
class SpecialAssignment:
    rule_code: str
    participant_id: str
    wave_no: int
    team_key: str


@dataclass(frozen=True, slots=True)
class TeamSummary:
    wave_no: int
    team_key: str
    member_count: int
    role_counts: dict[RoleType, int]
    damage_total: int
    buffer_total: int
    composition_code: str | None


@dataclass(frozen=True, slots=True)
class SolverResult:
    status: SolverStatus
    assignments: tuple[SolverAssignment, ...]
    special_assignments: tuple[SpecialAssignment, ...]
    unassigned_participant_ids: tuple[str, ...]
    team_summaries: tuple[TeamSummary, ...]
    objective_value: float | None
    wall_time_seconds: float
