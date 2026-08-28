from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from decimal import Decimal

from app.models.dungeon import DungeonVersion, FormulaVersion
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    SchedulePlayerPreference,
    WaveSpecialAssignment,
)
from app.schemas.dungeon import (
    DungeonVersionDefinition,
    FormulaDefinition,
    RoleType,
    TeamDefinition,
)
from app.solver import (
    LockedAssignment,
    LockedEmptySlot,
    SolverInput,
    SolverParticipant,
    SolverPlayerPreference,
    SolverResult,
)

SOLVER_VERSION = "cp-sat-v2"


def build_solver_input(
    schedule: Schedule,
    version: DungeonVersion,
    formula_version: FormulaVersion,
    *,
    preserve_locks: bool,
    random_seed: int,
    time_limit_seconds: int,
) -> SolverInput:
    formula = FormulaDefinition(
        code=formula_version.code,
        version=formula_version.version,
        **formula_version.config,
    )
    definition = DungeonVersionDefinition(
        dungeon_code=version.dungeon.code,
        dungeon_name=version.dungeon.name,
        description=version.dungeon.description,
        version_no=version.version_no,
        default_wave_count=version.default_wave_count,
        min_wave_count=version.min_wave_count,
        max_wave_count=version.max_wave_count,
        formula=formula,
        teams=tuple(
            TeamDefinition(
                team_key=team.team_key,
                display_name=team.display_name,
                display_color=team.display_color,
                display_order=team.display_order,
                member_count=team.member_count,
                strength_rank=team.strength_rank,
            )
            for team in version.teams
        ),
        composition_rules=version.composition_rules,
        special_role_rules=version.special_role_rules,
        strength_order_rules=version.strength_order_rules,
        optimization_rules=version.optimization_rules,
        missing_slot_policy=version.missing_slot_policy,
    )
    preference_by_player = {preference.player_id: preference for preference in schedule.preferences}
    participants = tuple(
        SolverParticipant(
            participant_id=str(participant.id),
            player_id=str(participant.player_id_snapshot),
            role_type=RoleType(participant.role_type_snapshot),
            score=(
                int(participant.damage_score_snapshot * formula.damage_scale)
                if participant.role_type_snapshot == RoleType.DAMAGE
                and participant.damage_score_snapshot is not None
                else int(participant.buffer_score_snapshot * formula.buffer_scale)
                if participant.buffer_score_snapshot is not None
                else 0
            ),
            is_treasure_damage=participant.is_treasure_snapshot,
            allowed_waves=_allowed_waves(participant.player_id_snapshot, preference_by_player),
        )
        for participant in schedule.participants
        if participant.is_selected
    )
    selected_player_ids = {participant.player_id for participant in participants}
    player_preferences = tuple(
        SolverPlayerPreference(
            player_id=str(preference.player_id),
            max_wave_count=preference.max_wave_count,
            prefer_early=preference.prefer_early,
            prefer_contiguous=preference.prefer_contiguous,
        )
        for preference in schedule.preferences
        if str(preference.player_id) in selected_player_ids
    )
    locked_assignments: list[LockedAssignment] = []
    locked_empty_slots: list[LockedEmptySlot] = []
    if preserve_locks:
        participant_by_id = {participant.id: participant for participant in schedule.participants}
        for wave in schedule.waves:
            for team in wave.teams:
                locked_empty_count = 0
                for slot in team.slots:
                    participant = (
                        participant_by_id.get(slot.participant_id)
                        if slot.participant_id is not None
                        else None
                    )
                    locked = (
                        wave.is_locked
                        or slot.is_locked
                        or bool(participant is not None and participant.is_locked)
                    )
                    if not locked:
                        continue
                    if participant is None:
                        locked_empty_count += 1
                    elif participant.is_selected:
                        locked_assignments.append(
                            LockedAssignment(str(participant.id), wave.wave_no, team.team_key)
                        )
                if locked_empty_count:
                    locked_empty_slots.append(
                        LockedEmptySlot(wave.wave_no, team.team_key, locked_empty_count)
                    )
    return SolverInput(
        schedule_id=str(schedule.id),
        revision=schedule.revision,
        dungeon=definition,
        wave_count=schedule.wave_count,
        participants=participants,
        player_preferences=player_preferences,
        locked_assignments=tuple(locked_assignments),
        locked_empty_slots=tuple(locked_empty_slots),
        random_seed=random_seed,
        time_limit_seconds=time_limit_seconds,
    )


def solver_input_hash(solver_input: SolverInput) -> str:
    payload = asdict(solver_input)
    payload["dungeon"] = solver_input.dungeon.model_dump(mode="json", by_alias=True)
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def apply_solver_result(
    schedule: Schedule,
    solver_input: SolverInput,
    result: SolverResult,
) -> dict[str, object]:
    participant_by_id = {str(participant.id): participant for participant in schedule.participants}

    special_ids = {assignment.participant_id for assignment in result.special_assignments}
    assignments_by_team: dict[tuple[int, str], list[str]] = {}
    for assignment in result.assignments:
        assignments_by_team.setdefault((assignment.wave_no, assignment.team_key), []).append(
            assignment.participant_id
        )
    wave_by_no = {wave.wave_no: wave for wave in schedule.waves}
    for (wave_no, team_key), participant_ids in assignments_by_team.items():
        team = next(team for team in wave_by_no[wave_no].teams if team.team_key == team_key)
        already_present = {str(slot.participant_id) for slot in team.slots if slot.participant_id}
        pending = [
            participant_id
            for participant_id in participant_ids
            if participant_id not in already_present
        ]
        pending.sort(
            key=lambda participant_id: (
                participant_id not in special_ids,
                participant_by_id[participant_id].role_type_snapshot != RoleType.DAMAGE,
                -_participant_score(participant_by_id[participant_id]),
                participant_id,
            )
        )
        free_slots = [
            slot for slot in team.slots if slot.participant_id is None and not slot.is_locked
        ]
        if len(pending) > len(free_slots):
            raise ValueError("求解结果超过可用位置容量")
        for participant_id, slot in zip(pending, free_slots, strict=False):
            slot.participant_id = uuid.UUID(participant_id)

    summary_by_team = {
        (summary.wave_no, summary.team_key): summary for summary in result.team_summaries
    }
    damage_scale = solver_input.dungeon.formula.damage_scale
    buffer_scale = solver_input.dungeon.formula.buffer_scale
    for wave in schedule.waves:
        wave_damage = 0
        wave_buffer = 0
        for team in wave.teams:
            summary = summary_by_team[wave.wave_no, team.team_key]
            team.damage_total = Decimal(summary.damage_total) / damage_scale
            team.buffer_total = Decimal(summary.buffer_total) / buffer_scale
            team.composition_code = summary.composition_code or "INCOMPLETE"
            wave_damage += summary.damage_total
            wave_buffer += summary.buffer_total
        wave.damage_total = Decimal(wave_damage) / damage_scale
        wave.buffer_total = Decimal(wave_buffer) / buffer_scale

    for special in result.special_assignments:
        wave = wave_by_no[special.wave_no]
        wave.special_assignments.append(
            WaveSpecialAssignment(
                id=uuid.uuid4(),
                schedule_id=schedule.id,
                wave_id=wave.id,
                rule_code=special.rule_code,
                participant_id=uuid.UUID(special.participant_id),
                target_team_key_snapshot=special.team_key,
            )
        )

    unassigned_by_id = {reason.participant_id: reason for reason in result.unassigned}
    for participant in schedule.participants:
        if not participant.is_selected:
            continue
        reason = unassigned_by_id.get(str(participant.id))
        participant.unassigned_reason = (
            {"code": reason.code, "messageParams": reason.message_params}
            if reason is not None
            else None
        )

    return {
        "solverStatus": result.status.value,
        "unassigned": [
            {
                "participantId": reason.participant_id,
                "code": reason.code,
                "messageParams": reason.message_params,
            }
            for reason in result.unassigned
        ],
        "issues": [
            {
                "severity": issue.severity,
                "code": issue.code,
                "messageParams": issue.message_params,
            }
            for issue in result.issues
        ],
    }


def clear_regeneratable_assignments(
    schedule: Schedule,
    solver_input: SolverInput,
    *,
    preserve_locks: bool,
) -> None:
    locked_participant_ids = {
        assignment.participant_id for assignment in solver_input.locked_assignments
    }
    for wave in schedule.waves:
        wave.special_assignments.clear()
        for team in wave.teams:
            for slot in team.slots:
                if not preserve_locks or (
                    not wave.is_locked
                    and not slot.is_locked
                    and str(slot.participant_id) not in locked_participant_ids
                ):
                    slot.participant_id = None


def objective_summary_payload(
    result: SolverResult, formula: FormulaDefinition
) -> dict[str, object]:
    summary = result.objective_summary
    return {
        "assignedCount": summary.assigned_count,
        "participantCount": summary.participant_count,
        "completeWaveCount": summary.complete_wave_count,
        "completeTeamCount": summary.complete_team_count,
        "preferredCompositionCount": summary.preferred_composition_count,
        "specialRuleSatisfiedCount": summary.special_rule_satisfied_count,
        "damageSpread": summary.damage_spread,
        "bufferSpread": summary.buffer_spread,
        "damageSpreadDisplay": str(Decimal(summary.damage_spread) / formula.damage_scale),
        "bufferSpreadDisplay": str(Decimal(summary.buffer_spread) / formula.buffer_scale),
        "strengthOrderViolationCount": summary.strength_order_violation_count,
    }


def _allowed_waves(
    player_id: uuid.UUID, preferences: dict[uuid.UUID, SchedulePlayerPreference]
) -> tuple[int, ...] | None:
    preference = preferences.get(player_id)
    allowed_waves = preference.allowed_waves if preference is not None else None
    return tuple(allowed_waves) if allowed_waves is not None else None


def _participant_score(participant: ScheduleParticipant) -> int:
    role_type = participant.role_type_snapshot
    score = (
        participant.damage_score_snapshot
        if role_type == RoleType.DAMAGE
        else participant.buffer_score_snapshot
    )
    return int((score or 0) * 100)
