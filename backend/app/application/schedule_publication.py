from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.dungeon import DungeonVersion
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    SchedulePlayerPreference,
    Team,
    TeamSlot,
    Wave,
    WaveSpecialAssignment,
)
from app.schemas.dungeon import SpecialRoleRules, StrengthOrderRules
from app.schemas.schedule import IssueView, ScheduleDetail

SNAPSHOT_SCHEMA_VERSION = 1


def create_schedule_snapshot(
    schedule: Schedule,
    version: DungeonVersion,
    issues: list[IssueView],
    published_at: datetime,
) -> tuple[dict[str, object], str]:
    snapshot = ScheduleDetail.model_validate(schedule).model_dump(mode="json", by_alias=True)
    snapshot["status"] = "PUBLISHED"
    snapshot["schemaVersion"] = SNAPSHOT_SCHEMA_VERSION
    snapshot["publishedAt"] = published_at.isoformat()
    snapshot["dungeon"] = {
        "id": str(version.dungeon_id),
        "code": version.dungeon.code,
        "name": version.dungeon.name,
        "versionId": str(version.id),
        "versionNo": version.version_no,
        "teams": [
            {
                "teamKey": team.team_key,
                "displayName": team.display_name,
                "displayColor": team.display_color,
                "displayOrder": team.display_order,
                "memberCount": team.member_count,
                "strengthRank": team.strength_rank,
            }
            for team in version.teams
        ],
        "compositionRules": version.composition_rules,
        "specialRoleRules": version.special_role_rules,
        "strengthOrderRules": version.strength_order_rules,
        "optimizationRules": version.optimization_rules,
        "missingSlotPolicy": version.missing_slot_policy,
    }
    snapshot["formula"] = {
        "id": str(version.formula_version.id),
        "code": version.formula_version.code,
        "version": version.formula_version.version,
        "config": version.formula_version.config,
    }
    snapshot["issues"] = [issue.model_dump(mode="json") for issue in issues]
    serialized = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return snapshot, hashlib.sha256(serialized).hexdigest()


def publication_issues(schedule: Schedule, version: DungeonVersion) -> list[IssueView]:
    issues: list[IssueView] = []
    participant_by_id = {participant.id: participant for participant in schedule.participants}
    preference_by_player = {preference.player_id: preference for preference in schedule.preferences}
    assigned_waves_by_player: dict[uuid.UUID, set[int]] = {}
    for wave in schedule.waves:
        players: dict[uuid.UUID, int] = {}
        for team in wave.teams:
            if team.composition_code == "INCOMPLETE":
                issues.append(
                    IssueView(
                        severity="ERROR",
                        code="TEAM_INCOMPLETE",
                        message_params={"waveNo": wave.wave_no, "teamKey": team.team_key},
                    )
                )
            elif team.composition_code == "INVALID":
                issues.append(
                    IssueView(
                        severity="ERROR",
                        code="TEAM_COMPOSITION_INVALID",
                        message_params={"waveNo": wave.wave_no, "teamKey": team.team_key},
                    )
                )
            for slot in team.slots:
                if slot.participant_id is None:
                    continue
                participant = participant_by_id[slot.participant_id]
                players[participant.player_id_snapshot] = (
                    players.get(participant.player_id_snapshot, 0) + 1
                )
                assigned_waves_by_player.setdefault(
                    participant.player_id_snapshot, set()
                ).add(wave.wave_no)
                preference = preference_by_player.get(participant.player_id_snapshot)
                if (
                    preference is not None
                    and preference.allowed_waves is not None
                    and wave.wave_no not in preference.allowed_waves
                ):
                    issues.append(
                        IssueView(
                            severity="ERROR",
                            code="PARTICIPANT_WAVE_NOT_ALLOWED",
                            message_params={
                                "waveNo": wave.wave_no,
                                "participantId": str(participant.id),
                                "playerId": str(participant.player_id_snapshot),
                            },
                        )
                    )
        for player_id, count in players.items():
            if count > 1:
                issues.append(
                    IssueView(
                        severity="ERROR",
                        code="PLAYER_DUPLICATE_IN_WAVE",
                        message_params={
                            "waveNo": wave.wave_no,
                            "playerId": str(player_id),
                            "count": count,
                        },
                    )
                )

    for player_id, assigned_waves in assigned_waves_by_player.items():
        preference = preference_by_player.get(player_id)
        if (
            preference is not None
            and preference.max_wave_count is not None
            and len(assigned_waves) > preference.max_wave_count
        ):
            issues.append(
                IssueView(
                    severity="ERROR",
                    code="PLAYER_MAX_WAVE_COUNT_EXCEEDED",
                    message_params={
                        "playerId": str(player_id),
                        "maximum": preference.max_wave_count,
                        "current": len(assigned_waves),
                    },
                )
            )

    special_rules = SpecialRoleRules.model_validate(version.special_role_rules)
    for wave in schedule.waves:
        for rule in special_rules.rules:
            actual = sum(
                assignment.rule_code == rule.code for assignment in wave.special_assignments
            )
            if rule.required_for_complete_wave and actual < rule.count_per_wave:
                issues.append(
                    IssueView(
                        severity="WARNING",
                        code="MISSING_WAVE_CORE",
                        message_params={
                            "waveNo": wave.wave_no,
                            "ruleCode": rule.code,
                            "required": rule.count_per_wave,
                            "current": actual,
                        },
                    )
                )

    orders = StrengthOrderRules.model_validate(version.strength_order_rules)
    for wave in schedule.waves:
        team_by_key = {team.team_key: team for team in wave.teams}
        for order in orders.orders:
            for stronger_key, weaker_key in zip(order.teams, order.teams[1:], strict=False):
                stronger_team = team_by_key[stronger_key]
                weaker_team = team_by_key[weaker_key]
                stronger = (
                    stronger_team.damage_total
                    if order.metric.value == "DAMAGE"
                    else stronger_team.buffer_total
                )
                weaker = (
                    weaker_team.damage_total
                    if order.metric.value == "DAMAGE"
                    else weaker_team.buffer_total
                )
                if stronger < weaker:
                    issues.append(
                        IssueView(
                            severity="WARNING",
                            code=f"{order.metric.value}_ORDER_VIOLATION",
                            message_params={
                                "waveNo": wave.wave_no,
                                "strongerTeamKey": stronger_key,
                                "weakerTeamKey": weaker_key,
                                "strongerValue": str(stronger),
                                "weakerValue": str(weaker),
                            },
                        )
                    )

    assigned_ids = {
        slot.participant_id
        for wave in schedule.waves
        for team in wave.teams
        for slot in team.slots
        if slot.participant_id is not None
    }
    unassigned = [
        participant
        for participant in schedule.participants
        if participant.is_selected and participant.id not in assigned_ids
    ]
    if unassigned:
        issues.append(
            IssueView(
                severity="WARNING",
                code="UNASSIGNED_SELECTED_PARTICIPANTS",
                message_params={"count": len(unassigned)},
            )
        )
    return issues


def restore_snapshot(
    db: Session,
    schedule: Schedule,
    snapshot: dict[str, object],
) -> None:
    schedule.waves.clear()
    db.flush()
    schedule.preferences.clear()
    schedule.participants.clear()
    db.flush()

    schedule.name = str(snapshot["name"])
    note = snapshot.get("note")
    schedule.note = str(note) if note is not None else None
    schedule.dungeon_version_id = uuid.UUID(str(snapshot["dungeonVersionId"]))
    schedule.wave_count = int(str(snapshot["waveCount"]))

    participant_rows = _list_of_dicts(snapshot.get("participants"))
    participant_id_map: dict[str, uuid.UUID] = {}
    for row in participant_rows:
        participant_id = uuid.uuid4()
        participant_id_map[str(row["id"])] = participant_id
        schedule.participants.append(
            ScheduleParticipant(
                id=participant_id,
                schedule_id=schedule.id,
                character_id=uuid.UUID(str(row["characterId"])),
                player_id_snapshot=uuid.UUID(str(row["playerIdSnapshot"])),
                player_name_snapshot=str(row["playerNameSnapshot"]),
                character_name_snapshot=str(row["characterNameSnapshot"]),
                profession_snapshot=str(row["professionSnapshot"]),
                role_type_snapshot=str(row["roleTypeSnapshot"]),
                damage_score_snapshot=_decimal_or_none(row.get("damageScoreSnapshot")),
                buffer_score_snapshot=_decimal_or_none(row.get("bufferScoreSnapshot")),
                is_treasure_snapshot=bool(row["isTreasureSnapshot"]),
                is_selected=bool(row["isSelected"]),
                is_locked=bool(row["isLocked"]),
                unassigned_reason=row.get("unassignedReason"),
            )
        )
    for row in _list_of_dicts(snapshot.get("preferences")):
        allowed = row.get("allowedWaves")
        schedule.preferences.append(
            SchedulePlayerPreference(
                schedule_id=schedule.id,
                player_id=uuid.UUID(str(row["playerId"])),
                allowed_waves=(
                    [int(value) for value in allowed] if isinstance(allowed, list) else None
                ),
                max_wave_count=(
                    int(str(row["maxWaveCount"]))
                    if row.get("maxWaveCount") is not None
                    else None
                ),
                prefer_early=bool(row["preferEarly"]),
                prefer_contiguous=bool(row["preferContiguous"]),
            )
        )
    db.flush()

    for wave_row in _list_of_dicts(snapshot.get("waves")):
        wave_id = uuid.uuid4()
        wave = Wave(
            id=wave_id,
            schedule_id=schedule.id,
            wave_no=int(str(wave_row["waveNo"])),
            is_locked=bool(wave_row["isLocked"]),
            damage_total=Decimal(str(wave_row["damageTotal"])),
            buffer_total=Decimal(str(wave_row["bufferTotal"])),
        )
        for team_row in _list_of_dicts(wave_row.get("teams")):
            team_id = uuid.uuid4()
            team = Team(
                id=team_id,
                schedule_id=schedule.id,
                wave_id=wave_id,
                team_key=str(team_row["teamKey"]),
                display_name_snapshot=str(team_row["displayNameSnapshot"]),
                display_color_snapshot=str(team_row["displayColorSnapshot"]),
                display_order_snapshot=int(str(team_row["displayOrderSnapshot"])),
                member_count_snapshot=int(str(team_row["memberCountSnapshot"])),
                strength_rank_snapshot=(
                    int(str(team_row["strengthRankSnapshot"]))
                    if team_row.get("strengthRankSnapshot") is not None
                    else None
                ),
                damage_total=Decimal(str(team_row["damageTotal"])),
                buffer_total=Decimal(str(team_row["bufferTotal"])),
                composition_code=str(team_row["compositionCode"]),
            )
            for slot_row in _list_of_dicts(team_row.get("slots")):
                snapshot_participant_id = slot_row.get("participantId")
                team.slots.append(
                    TeamSlot(
                        id=uuid.uuid4(),
                        schedule_id=schedule.id,
                        wave_id=wave_id,
                        team_id=team_id,
                        slot_no=int(str(slot_row["slotNo"])),
                        participant_id=(
                            participant_id_map[str(snapshot_participant_id)]
                            if snapshot_participant_id is not None
                            else None
                        ),
                        is_locked=bool(slot_row["isLocked"]),
                    )
                )
            wave.teams.append(team)
        for special_row in _list_of_dicts(wave_row.get("specialAssignments")):
            wave.special_assignments.append(
                WaveSpecialAssignment(
                    id=uuid.uuid4(),
                    schedule_id=schedule.id,
                    wave_id=wave_id,
                    rule_code=str(special_row["ruleCode"]),
                    participant_id=participant_id_map[str(special_row["participantId"])],
                    target_team_key_snapshot=str(special_row["targetTeamKeySnapshot"]),
                )
            )
        schedule.waves.append(wave)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("发布版本快照结构无效")
    return value


def _decimal_or_none(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
