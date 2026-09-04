from dataclasses import dataclass
from enum import StrEnum

from app.schemas.dungeon import DungeonVersionDefinition, RoleType


class SolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    PARTIAL = "PARTIAL"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ObjectiveStageOutcome(StrEnum):
    OPTIMAL = "OPTIMAL"
    TARGET_REACHED = "TARGET_REACHED"
    FEASIBLE = "FEASIBLE"


class SolverScheduleRuleType(StrEnum):
    PLAYER_ALLOWED_WAVES = "PLAYER_ALLOWED_WAVES"
    PLAYER_FORBIDDEN_WAVES = "PLAYER_FORBIDDEN_WAVES"
    PLAYERS_NOT_SAME_WAVE = "PLAYERS_NOT_SAME_WAVE"
    CHARACTER_REQUIRED_WAVE = "CHARACTER_REQUIRED_WAVE"
    CHARACTER_REQUIRED_TEAM = "CHARACTER_REQUIRED_TEAM"
    PLAYER_PREFER_WAVE_RANGE = "PLAYER_PREFER_WAVE_RANGE"
    PLAYER_PREFER_CONTIGUOUS = "PLAYER_PREFER_CONTIGUOUS"
    CHARACTER_PREFER_TEAM = "CHARACTER_PREFER_TEAM"


@dataclass(frozen=True, slots=True)
class SolverScheduleRule:
    rule_id: str
    type: SolverScheduleRuleType
    explanation: str = ""
    player_ids: tuple[str, ...] = ()
    participant_id: str | None = None
    waves: tuple[int, ...] = ()
    team_key: str | None = None


@dataclass(frozen=True, slots=True)
class SolverParticipant:
    participant_id: str
    player_id: str
    role_type: RoleType
    score: int
    is_treasure_damage: bool = False
    allowed_waves: tuple[int, ...] | None = None
    allowed_team_keys: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SolverPlayerPreference:
    player_id: str
    max_wave_count: int | None = None
    prefer_early: bool = False
    prefer_contiguous: bool = False


@dataclass(frozen=True, slots=True)
class LockedAssignment:
    participant_id: str
    wave_no: int
    team_key: str


@dataclass(frozen=True, slots=True)
class LockedEmptySlot:
    wave_no: int
    team_key: str
    count: int = 1


@dataclass(frozen=True, slots=True)
class SolverInput:
    dungeon: DungeonVersionDefinition
    wave_count: int
    participants: tuple[SolverParticipant, ...]
    schedule_id: str | None = None
    revision: int = 1
    player_preferences: tuple[SolverPlayerPreference, ...] = ()
    schedule_rules: tuple[SolverScheduleRule, ...] = ()
    locked_assignments: tuple[LockedAssignment, ...] = ()
    locked_empty_slots: tuple[LockedEmptySlot, ...] = ()
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
class UnassignedReason:
    participant_id: str
    code: str
    message_params: dict[str, object]


@dataclass(frozen=True, slots=True)
class SolverIssue:
    severity: str
    code: str
    message_params: dict[str, object]


@dataclass(frozen=True, slots=True)
class ObjectiveSummary:
    assigned_count: int
    participant_count: int
    complete_wave_count: int
    complete_team_count: int
    preferred_composition_count: int
    special_rule_satisfied_count: int
    damage_spread: int
    buffer_spread: int
    strength_order_violation_count: int


@dataclass(frozen=True, slots=True)
class ObjectiveStageResult:
    code: str
    value: int
    outcome: ObjectiveStageOutcome
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class SolverResult:
    status: SolverStatus
    assignments: tuple[SolverAssignment, ...]
    special_assignments: tuple[SpecialAssignment, ...]
    unassigned_participant_ids: tuple[str, ...]
    unassigned: tuple[UnassignedReason, ...]
    team_summaries: tuple[TeamSummary, ...]
    issues: tuple[SolverIssue, ...]
    objective_summary: ObjectiveSummary
    objective_value: float | None
    wall_time_seconds: float
    objective_stages: tuple[ObjectiveStageResult, ...] = ()
