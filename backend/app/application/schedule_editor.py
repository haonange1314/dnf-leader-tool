from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.dungeon import DungeonVersion
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    Team,
    TeamSlot,
    Wave,
    WaveSpecialAssignment,
)
from app.schemas.dungeon import CompositionRules, SpecialRoleRules
from app.schemas.schedule import ScheduleOperation


def apply_schedule_operations(
    db: Session,
    schedule: Schedule,
    version: DungeonVersion,
    operations: list[ScheduleOperation],
) -> list[ScheduleOperation]:
    participants = {participant.id: participant for participant in schedule.participants}
    waves = {wave.id: wave for wave in schedule.waves}
    slots = {
        slot.id: slot
        for wave in schedule.waves
        for team in wave.teams
        for slot in team.slots
    }
    special_before = [
        (wave.id, assignment.rule_code, assignment.participant_id)
        for wave in schedule.waves
        for assignment in wave.special_assignments
    ]
    inverse_operations: list[ScheduleOperation] = []
    for operation in operations:
        inverse = _apply_operation(
            db,
            schedule,
            version,
            operation,
            participants=participants,
            waves=waves,
            slots=slots,
        )
        inverse_operations.insert(0, inverse)
    recompute_schedule(schedule, version)
    explicit_special_keys = {
        (operation.wave_id, operation.rule_code)
        for operation in operations
        if operation.type in ("SET_WAVE_CORE", "CLEAR_WAVE_CORE")
    }
    special_after = {
        (wave.id, assignment.rule_code, assignment.participant_id)
        for wave in schedule.waves
        for assignment in wave.special_assignments
    }
    for wave_id, rule_code, participant_id in special_before:
        if (
            (wave_id, rule_code, participant_id) not in special_after
            and (wave_id, rule_code) not in explicit_special_keys
            and (wave_id, None) not in explicit_special_keys
        ):
            inverse_operations.append(
                ScheduleOperation(
                    type="SET_WAVE_CORE",
                    wave_id=wave_id,
                    rule_code=rule_code,
                    participant_id=participant_id,
                )
            )
    return inverse_operations


def recompute_schedule(schedule: Schedule, version: DungeonVersion) -> None:
    participant_by_id = {participant.id: participant for participant in schedule.participants}
    composition_rules = CompositionRules.model_validate(version.composition_rules)
    locations: dict[uuid.UUID, tuple[Wave, Team, TeamSlot]] = {}
    for wave in schedule.waves:
        wave_damage = Decimal(0)
        wave_buffer = Decimal(0)
        for team in wave.teams:
            members = [
                participant_by_id[slot.participant_id]
                for slot in team.slots
                if slot.participant_id is not None
            ]
            for slot in team.slots:
                if slot.participant_id is not None:
                    locations[slot.participant_id] = (wave, team, slot)
            team.damage_total = sum(
                (
                    member.damage_score_snapshot or Decimal(0)
                    for member in members
                    if member.role_type_snapshot == "DAMAGE"
                ),
                Decimal(0),
            )
            team.buffer_total = sum(
                (
                    member.buffer_score_snapshot or Decimal(0)
                    for member in members
                    if member.role_type_snapshot == "BUFFER"
                ),
                Decimal(0),
            )
            role_counts = {
                "DAMAGE": sum(member.role_type_snapshot == "DAMAGE" for member in members),
                "BUFFER": sum(member.role_type_snapshot == "BUFFER" for member in members),
            }
            if len(members) < team.member_count_snapshot:
                team.composition_code = "INCOMPLETE"
            else:
                team.composition_code = next(
                    (
                        rule.code
                        for rule in composition_rules.allowed
                        if team.team_key in rule.applicable_team_keys
                        and all(
                            role_counts[role.value] == rule.roles.get(role, 0)
                            for role in rule.roles
                        )
                    ),
                    "INVALID",
                )
            wave_damage += team.damage_total
            wave_buffer += team.buffer_total
        wave.damage_total = wave_damage
        wave.buffer_total = wave_buffer

        for special in list(wave.special_assignments):
            location = locations.get(special.participant_id)
            participant = participant_by_id.get(special.participant_id)
            if (
                location is None
                or location[0].id != wave.id
                or location[1].team_key != special.target_team_key_snapshot
                or participant is None
                or participant.role_type_snapshot != "DAMAGE"
                or not participant.is_treasure_snapshot
            ):
                wave.special_assignments.remove(special)

    for participant in schedule.participants:
        if participant.id in locations:
            participant.unassigned_reason = None


def _apply_operation(
    db: Session,
    schedule: Schedule,
    version: DungeonVersion,
    operation: ScheduleOperation,
    *,
    participants: dict[uuid.UUID, ScheduleParticipant],
    waves: dict[uuid.UUID, Wave],
    slots: dict[uuid.UUID, TeamSlot],
) -> ScheduleOperation:
    if operation.type == "MOVE_PARTICIPANT":
        participant = _participant(operation.participant_id, participants)
        target = _slot(operation.to_slot_id, slots)
        source = _participant_slot(schedule, participant.id)
        _ensure_move_allowed(participant, source, target)
        if target.participant_id is not None and target.participant_id != participant.id:
            raise AppError(422, "TARGET_SLOT_OCCUPIED", "目标位置已有角色，请使用交换操作")
        if source is not None and source.id == target.id:
            raise AppError(422, "SCHEDULE_OPERATION_NO_CHANGE", "角色已在目标位置")
        if source is not None:
            source.participant_id = None
            db.flush()
        target.participant_id = participant.id
        return (
            ScheduleOperation(
                type="MOVE_PARTICIPANT",
                participant_id=participant.id,
                to_slot_id=source.id,
            )
            if source is not None
            else ScheduleOperation(type="UNASSIGN_PARTICIPANT", participant_id=participant.id)
        )

    if operation.type == "SWAP_PARTICIPANTS":
        participant = _participant(operation.participant_id, participants)
        other = _participant(operation.other_participant_id, participants)
        if participant.id == other.id:
            raise AppError(422, "SCHEDULE_OPERATION_NO_CHANGE", "不能与同一角色交换")
        swap_source = _participant_slot(schedule, participant.id)
        swap_target = _participant_slot(schedule, other.id)
        if swap_source is None or swap_target is None:
            raise AppError(422, "SWAP_PARTICIPANT_UNASSIGNED", "交换双方都必须已在排表中")
        _ensure_move_allowed(participant, swap_source, swap_target)
        _ensure_move_allowed(other, swap_target, swap_source)
        swap_source.participant_id = None
        swap_target.participant_id = None
        db.flush()
        swap_source.participant_id = other.id
        swap_target.participant_id = participant.id
        return ScheduleOperation(
            type="SWAP_PARTICIPANTS",
            participant_id=participant.id,
            other_participant_id=other.id,
        )

    if operation.type == "UNASSIGN_PARTICIPANT":
        participant = _participant(operation.participant_id, participants)
        source = _participant_slot(schedule, participant.id)
        if source is None:
            raise AppError(422, "PARTICIPANT_ALREADY_UNASSIGNED", "角色已经位于未分配池")
        _ensure_move_allowed(participant, source, None)
        source.participant_id = None
        participant.unassigned_reason = {"code": "MANUALLY_UNASSIGNED", "messageParams": {}}
        return ScheduleOperation(
            type="MOVE_PARTICIPANT", participant_id=participant.id, to_slot_id=source.id
        )

    if operation.type == "LOCK_PARTICIPANT":
        participant = _participant(operation.participant_id, participants)
        locked = _required_bool(operation.locked)
        participant_was_locked = participant.is_locked
        participant.is_locked = locked
        return ScheduleOperation(
            type="LOCK_PARTICIPANT", participant_id=participant.id, locked=participant_was_locked
        )

    if operation.type == "LOCK_SLOT":
        slot = _slot(operation.slot_id, slots)
        locked = _required_bool(operation.locked)
        slot_was_locked = slot.is_locked
        slot.is_locked = locked
        return ScheduleOperation(type="LOCK_SLOT", slot_id=slot.id, locked=slot_was_locked)

    if operation.type == "LOCK_WAVE":
        wave = _wave(operation.wave_id, waves)
        locked = _required_bool(operation.locked)
        wave_was_locked = wave.is_locked
        wave.is_locked = locked
        return ScheduleOperation(type="LOCK_WAVE", wave_id=wave.id, locked=wave_was_locked)

    if operation.type in ("SET_WAVE_CORE", "CLEAR_WAVE_CORE"):
        wave = _wave(operation.wave_id, waves)
        rule_code = operation.rule_code
        special_rules = SpecialRoleRules.model_validate(version.special_role_rules)
        if (
            rule_code is None
            and operation.type == "SET_WAVE_CORE"
            and len(special_rules.rules) == 1
        ):
            rule_code = special_rules.rules[0].code
        if not rule_code:
            raise AppError(422, "SPECIAL_RULE_REQUIRED", "必须指定特殊角色规则")
        previous_core = next(
            (item for item in wave.special_assignments if item.rule_code == rule_code), None
        )
        if previous_core is not None:
            wave.special_assignments.remove(previous_core)
        if operation.type == "CLEAR_WAVE_CORE":
            if previous_core is None:
                raise AppError(422, "WAVE_CORE_NOT_SET", "该波次尚未设置核心角色")
            return ScheduleOperation(
                type="SET_WAVE_CORE",
                wave_id=wave.id,
                rule_code=rule_code,
                participant_id=previous_core.participant_id,
            )

        participant = _participant(operation.participant_id, participants)
        rule = next((item for item in special_rules.rules if item.code == rule_code), None)
        if rule is None:
            raise AppError(422, "SPECIAL_RULE_NOT_FOUND", "副本版本中不存在该特殊角色规则")
        location = _participant_location(schedule, participant.id)
        if (
            location is None
            or location[0].id != wave.id
            or location[1].team_key != rule.target_team_key
        ):
            raise AppError(422, "WAVE_CORE_WRONG_TEAM", "核心角色必须位于该波次的目标队伍")
        if participant.role_type_snapshot != "DAMAGE" or not participant.is_treasure_snapshot:
            raise AppError(422, "WAVE_CORE_INELIGIBLE", "只有秘宝 C 可以设置为本波核心")
        wave.special_assignments.append(
            WaveSpecialAssignment(
                id=uuid.uuid4(),
                schedule_id=schedule.id,
                wave_id=wave.id,
                rule_code=rule.code,
                participant_id=participant.id,
                target_team_key_snapshot=rule.target_team_key,
            )
        )
        return (
            ScheduleOperation(
                type="SET_WAVE_CORE",
                wave_id=wave.id,
                rule_code=rule_code,
                participant_id=previous_core.participant_id,
            )
            if previous_core is not None
            else ScheduleOperation(type="CLEAR_WAVE_CORE", wave_id=wave.id, rule_code=rule_code)
        )

    raise AppError(422, "SCHEDULE_OPERATION_UNSUPPORTED", "不支持的排表编辑操作")


def _participant(
    participant_id: uuid.UUID | None,
    participants: dict[uuid.UUID, ScheduleParticipant],
) -> ScheduleParticipant:
    if participant_id is None or participant_id not in participants:
        raise AppError(422, "PARTICIPANT_NOT_FOUND", "参团角色不存在")
    participant = participants[participant_id]
    if not participant.is_selected:
        raise AppError(422, "PARTICIPANT_NOT_SELECTED", "角色未被选为参团角色")
    return participant


def _slot(slot_id: uuid.UUID | None, slots: dict[uuid.UUID, TeamSlot]) -> TeamSlot:
    if slot_id is None or slot_id not in slots:
        raise AppError(422, "SLOT_NOT_FOUND", "排表位置不存在")
    return slots[slot_id]


def _wave(wave_id: uuid.UUID | None, waves: dict[uuid.UUID, Wave]) -> Wave:
    if wave_id is None or wave_id not in waves:
        raise AppError(422, "WAVE_NOT_FOUND", "波次不存在")
    return waves[wave_id]


def _required_bool(value: bool | None) -> bool:
    if value is None:
        raise AppError(422, "LOCK_STATE_REQUIRED", "必须指定锁定状态")
    return value


def _participant_slot(schedule: Schedule, participant_id: uuid.UUID) -> TeamSlot | None:
    location = _participant_location(schedule, participant_id)
    return location[2] if location is not None else None


def _participant_location(
    schedule: Schedule, participant_id: uuid.UUID
) -> tuple[Wave, Team, TeamSlot] | None:
    for wave in schedule.waves:
        for team in wave.teams:
            for slot in team.slots:
                if slot.participant_id == participant_id:
                    return wave, team, slot
    return None


def _ensure_move_allowed(
    participant: ScheduleParticipant,
    source: TeamSlot | None,
    target: TeamSlot | None,
) -> None:
    if participant.is_locked:
        raise AppError(422, "PARTICIPANT_LOCKED", "角色已锁定，不能移动")
    for slot in (source, target):
        if slot is None:
            continue
        if slot.is_locked:
            raise AppError(422, "SLOT_LOCKED", "位置已锁定，不能移动")
        if slot.team.wave.is_locked:
            raise AppError(422, "WAVE_LOCKED", "波次已锁定，不能移动")
