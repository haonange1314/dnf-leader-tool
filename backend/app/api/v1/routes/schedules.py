import hashlib
import json
import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    ScheduleDeleterEditor,
    ScheduleEditor,
    SchedulePublisherEditor,
    ScheduleReader,
    ScheduleWriter,
    enforce_schedule_edit_lock,
)
from app.application.schedule_rules import invalidate_active_rule_set
from app.core.errors import AppError
from app.domain.schedule import (
    MAX_SCHEDULE_POSITIONS,
    composition_feasibility,
    composition_role_requirements,
    distinct_player_feasibility,
)
from app.models.dungeon import DungeonVersion
from app.models.personnel import Character, Player
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    SchedulePlayerPreference,
    ScheduleRuleSet,
    ScheduleVersion,
    Team,
    TeamSlot,
    Wave,
)
from app.schemas.dungeon import CompositionRules, SpecialRoleRules, StrengthOrderRules
from app.schemas.schedule import (
    IssueView,
    ScheduleCopy,
    ScheduleCopyChange,
    ScheduleCopyPreview,
    ScheduleCopyPreviewRequest,
    ScheduleCreate,
    ScheduleDeleteRequest,
    ScheduleDetail,
    ScheduleLifecycleRequest,
    ScheduleList,
    ScheduleParticipantsUpdate,
    SchedulePreferencesUpdate,
    ScheduleSummary,
    ScheduleSyncChange,
    ScheduleSyncCommit,
    ScheduleSyncPreview,
    ScheduleUpdate,
    ValidationReport,
    ValidationRequest,
)

router = APIRouter()


def _load(db: DbSession, schedule_id: uuid.UUID, *, for_update: bool = False) -> Schedule:
    statement = (
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(
            selectinload(Schedule.participants),
            selectinload(Schedule.preferences),
            selectinload(Schedule.waves).selectinload(Wave.special_assignments),
            selectinload(Schedule.waves).selectinload(Wave.teams).selectinload(Team.slots),
            selectinload(Schedule.active_rule_set),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    item = db.scalar(statement)
    if item is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    return item


def _copy_preview(
    db: DbSession,
    source: Schedule,
    payload: ScheduleCopyPreviewRequest,
) -> tuple[DungeonVersion, ScheduleCopyPreview]:
    source_version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == source.dungeon_version_id)
        .options(selectinload(DungeonVersion.teams))
    )
    if source_version is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "源排表引用的副本版本不存在")
    target_id = payload.target_dungeon_version_id or source.dungeon_version_id
    target_version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == target_id)
        .options(selectinload(DungeonVersion.teams))
    )
    if target_version is None:
        raise AppError(422, "COPY_TARGET_VERSION_NOT_FOUND", "目标副本版本不存在")
    if target_version.dungeon_id != source_version.dungeon_id:
        raise AppError(422, "COPY_TARGET_DUNGEON_MISMATCH", "只能迁移到同一副本的版本")
    if target_version.id != source_version.id and target_version.status != "PUBLISHED":
        raise AppError(422, "COPY_TARGET_VERSION_NOT_PUBLISHED", "目标副本版本必须已发布")

    wave_count = payload.wave_count or source.wave_count
    if wave_count < target_version.min_wave_count or (
        target_version.max_wave_count is not None
        and wave_count > target_version.max_wave_count
    ):
        raise AppError(422, "WAVE_COUNT_OUT_OF_RANGE", "波数超出目标副本版本允许范围")
    target_positions_per_wave = sum(team.member_count for team in target_version.teams)
    if wave_count * target_positions_per_wave > MAX_SCHEDULE_POSITIONS:
        raise AppError(
            422,
            "SCHEDULE_POSITION_LIMIT_EXCEEDED",
            f"排表总位置数不能超过 {MAX_SCHEDULE_POSITIONS}",
        )

    source_teams = source.waves[0].teams
    source_shape = [
        {
            "teamKey": team.team_key,
            "displayName": team.display_name_snapshot,
            "displayColor": team.display_color_snapshot,
            "displayOrder": team.display_order_snapshot,
            "memberCount": team.member_count_snapshot,
            "strengthRank": team.strength_rank_snapshot,
        }
        for team in source_teams
    ]
    target_shape = [
        {
            "teamKey": team.team_key,
            "displayName": team.display_name,
            "displayColor": team.display_color,
            "displayOrder": team.display_order,
            "memberCount": team.member_count,
            "strengthRank": team.strength_rank,
        }
        for team in target_version.teams
    ]
    changes: list[ScheduleCopyChange] = []
    if target_version.id != source_version.id:
        changes.append(
            ScheduleCopyChange(
                code="DUNGEON_VERSION_CHANGED",
                description="副本版本将发生变化",
                before=source_version.version_no,
                after=target_version.version_no,
            )
        )
    if source.wave_count != wave_count:
        changes.append(
            ScheduleCopyChange(
                code="WAVE_COUNT_CHANGED",
                description="排表波数将发生变化",
                before=source.wave_count,
                after=wave_count,
            )
        )
    if source_shape != target_shape:
        changes.append(
            ScheduleCopyChange(
                code="TEAM_STRUCTURE_CHANGED",
                description="队伍数量、容量或展示配置将按目标版本重建",
                before=source_shape,
                after=target_shape,
            )
        )
    rule_fields = {
        "COMPOSITION_RULES_CHANGED": ("组成规则将发生变化", "composition_rules"),
        "SPECIAL_ROLE_RULES_CHANGED": ("特殊角色规则将发生变化", "special_role_rules"),
        "STRENGTH_ORDER_RULES_CHANGED": ("队伍强度顺序将发生变化", "strength_order_rules"),
        "OPTIMIZATION_RULES_CHANGED": ("跨波优化规则将发生变化", "optimization_rules"),
        "MISSING_SLOT_POLICY_CHANGED": ("空位策略将发生变化", "missing_slot_policy"),
    }
    for code, (description, field) in rule_fields.items():
        before = getattr(source_version, field)
        after = getattr(target_version, field)
        if before != after:
            changes.append(
                ScheduleCopyChange(
                    code=code,
                    description=description,
                    before=before,
                    after=after,
                )
            )
    if source.formula_version_id != target_version.formula_version_id:
        changes.append(
            ScheduleCopyChange(
                code="FORMULA_VERSION_CHANGED",
                description="评分公式版本将发生变化",
                before=str(source.formula_version_id),
                after=str(target_version.formula_version_id),
            )
        )
    fingerprint_state = {
        "sourceScheduleId": str(source.id),
        "sourceRevision": source.revision,
        "sourceDungeonVersionId": str(source_version.id),
        "targetDungeonVersionId": str(target_version.id),
        "waveCount": wave_count,
        "changes": [change.model_dump(mode="json", by_alias=True) for change in changes],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return target_version, ScheduleCopyPreview(
        revision=source.revision,
        source_dungeon_version_id=source_version.id,
        target_dungeon_version_id=target_version.id,
        wave_count=wave_count,
        migration_required=target_version.id != source_version.id,
        migration_fingerprint=fingerprint,
        changes=changes,
    )


def _claim_revision(
    db: DbSession, item: Schedule, base_revision: int, current_user: CurrentUser
) -> int:
    if item.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能修改")
    if item.revision != base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": base_revision, "current": item.revision},
        )
    new_revision = db.scalar(
        update(Schedule)
        .where(Schedule.id == item.id, Schedule.revision == base_revision)
        .values(
            revision=Schedule.revision + 1,
            status="DRAFT",
            updated_by=current_user.id,
            updated_at=func.now(),
        )
        .returning(Schedule.revision)
    )
    if new_revision is None:
        db.rollback()
        current_revision = db.scalar(select(Schedule.revision).where(Schedule.id == item.id))
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": base_revision, "current": current_revision},
        )
    return new_revision


def _new_wave_from_snapshot(
    schedule: Schedule, wave_no: int, team_templates: list[Team]
) -> Wave:
    wave = Wave(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        wave_no=wave_no,
        is_locked=False,
        damage_total=0,
        buffer_total=0,
    )
    for template in team_templates:
        team = Team(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            team_key=template.team_key,
            display_name_snapshot=template.display_name_snapshot,
            display_color_snapshot=template.display_color_snapshot,
            display_order_snapshot=template.display_order_snapshot,
            member_count_snapshot=template.member_count_snapshot,
            strength_rank_snapshot=template.strength_rank_snapshot,
            damage_total=0,
            buffer_total=0,
            composition_code="INCOMPLETE",
        )
        team.slots.extend(
            TeamSlot(
                id=uuid.uuid4(),
                schedule_id=schedule.id,
                wave_id=wave.id,
                team_id=team.id,
                slot_no=slot_no,
                is_locked=False,
            )
            for slot_no in range(1, template.member_count_snapshot + 1)
        )
        wave.teams.append(team)
    return wave


def _sync_source_state(
    db: DbSession, item: Schedule
) -> tuple[list[Character], str]:
    existing_character_ids = {
        participant.character_id for participant in item.participants
    }
    characters = list(
        db.scalars(
            select(Character)
            .join(Player, Character.player_id == Player.id)
            .where(
                Character.id.in_(existing_character_ids)
                | (
                    Character.is_active.is_(True)
                    & Character.default_raid_participant.is_(True)
                    & Player.is_active.is_(True)
                )
            )
            .options(selectinload(Character.player))
            .order_by(Character.id)
        )
    )
    state = [
        {
            "id": str(character.id),
            "playerId": str(character.player_id),
            "playerName": character.player.display_name,
            "playerActive": character.player.is_active,
            "name": character.profession,
            "profession": character.profession,
            "roleType": character.role_type,
            "damageScore": (
                str(character.damage_score) if character.damage_score is not None else None
            ),
            "bufferScore": (
                str(character.buffer_score) if character.buffer_score is not None else None
            ),
            "treasure": character.is_treasure_damage,
            "fixedLeadTeamBuffer": character.is_fixed_lead_team_buffer,
            "groupHunt": character.is_group_hunt,
            "defaultParticipant": character.default_raid_participant,
            "active": character.is_active,
        }
        for character in characters
    ]
    fingerprint = hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return characters, fingerprint


def _sync_changes(
    item: Schedule, characters: list[Character]
) -> list[ScheduleSyncChange]:
    participant_by_character = {
        participant.character_id: participant for participant in item.participants
    }
    changes: list[ScheduleSyncChange] = []
    for character in characters:
        participant = participant_by_character.get(character.id)
        active = character.is_active and character.player.is_active
        if participant is None:
            if active and character.default_raid_participant:
                changes.append(
                    ScheduleSyncChange(
                        action="ADD",
                        character_id=character.id,
                        player_name=character.player.display_name,
                        character_name=character.profession,
                        changed_fields=[],
                    )
                )
            continue
        if not active:
            if participant.is_selected:
                changes.append(
                    ScheduleSyncChange(
                        action="DESELECT",
                        character_id=character.id,
                        player_name=character.player.display_name,
                        character_name=character.profession,
                        changed_fields=["isSelected"],
                    )
                )
            continue
        current_values = {
            "playerName": participant.player_name_snapshot,
            "characterName": participant.character_name_snapshot,
            "profession": participant.profession_snapshot,
            "roleType": participant.role_type_snapshot,
            "damageScore": participant.damage_score_snapshot,
            "bufferScore": participant.buffer_score_snapshot,
            "isTreasure": participant.is_treasure_snapshot,
            "isFixedLeadTeamBuffer": participant.is_fixed_lead_team_buffer_snapshot,
            "isGroupHunt": participant.is_group_hunt_snapshot,
        }
        source_values = {
            "playerName": character.player.display_name,
            "characterName": character.profession,
            "profession": character.profession,
            "roleType": character.role_type,
            "damageScore": character.damage_score,
            "bufferScore": character.buffer_score,
            "isTreasure": character.is_treasure_damage,
            "isFixedLeadTeamBuffer": character.is_fixed_lead_team_buffer,
            "isGroupHunt": character.is_group_hunt,
        }
        changed_fields = [
            field for field, current in current_values.items() if current != source_values[field]
        ]
        if changed_fields:
            changes.append(
                ScheduleSyncChange(
                    action="UPDATE",
                    character_id=character.id,
                    player_name=character.player.display_name,
                    character_name=character.profession,
                    changed_fields=changed_fields,
                )
            )
    return changes


@router.get("", response_model=ScheduleList)
def list_schedules(
    db: DbSession,
    current_user: ScheduleReader,
    include_archived: bool = Query(default=False, alias="includeArchived"),
) -> ScheduleList:
    del current_user
    statement = select(Schedule).order_by(Schedule.updated_at.desc())
    if not include_archived:
        statement = statement.where(Schedule.status != "ARCHIVED")
    items = list(db.scalars(statement))
    db.commit()
    return ScheduleList(
        items=[ScheduleSummary.model_validate(item) for item in items], total=len(items)
    )


@router.post("", response_model=ScheduleDetail, status_code=201)
def create_schedule(
    payload: ScheduleCreate, db: DbSession, current_user: ScheduleWriter
) -> Schedule:
    version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == payload.dungeon_version_id)
        .options(
            selectinload(DungeonVersion.teams),
            selectinload(DungeonVersion.dungeon),
        )
    )
    if version is None or version.status != "PUBLISHED":
        raise AppError(422, "DUNGEON_VERSION_NOT_PUBLISHED", "只能使用已发布副本版本")
    if not version.dungeon.is_active:
        raise AppError(422, "DUNGEON_INACTIVE", "已停用副本不能创建新排表")
    wave_count = payload.wave_count or version.default_wave_count
    if wave_count < version.min_wave_count or (
        version.max_wave_count is not None and wave_count > version.max_wave_count
    ):
        raise AppError(422, "WAVE_COUNT_OUT_OF_RANGE", "波数超出副本允许范围")
    position_count = wave_count * sum(team.member_count for team in version.teams)
    if position_count > MAX_SCHEDULE_POSITIONS:
        raise AppError(
            422,
            "SCHEDULE_POSITION_LIMIT_EXCEEDED",
            f"排表总位置数不能超过 {MAX_SCHEDULE_POSITIONS}",
            details={"limit": MAX_SCHEDULE_POSITIONS, "current": position_count},
        )
    schedule = Schedule(
        id=uuid.uuid4(),
        name=payload.name,
        dungeon_version_id=version.id,
        formula_version_id=version.formula_version_id,
        wave_count=wave_count,
        status="DRAFT",
        note=payload.note,
        revision=1,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    characters = list(
        db.scalars(
            select(Character)
            .join(Player, Character.player_id == Player.id)
            .where(
                Character.is_active.is_(True),
                Character.default_raid_participant.is_(True),
                Player.is_active.is_(True),
            )
            .options(selectinload(Character.player))
        )
    )
    players: set[uuid.UUID] = set()
    for character in characters:
        schedule.participants.append(
            ScheduleParticipant(
                character_id=character.id,
                player_id_snapshot=character.player_id,
                player_name_snapshot=character.player.display_name,
                character_name_snapshot=character.profession,
                profession_snapshot=character.profession,
                role_type_snapshot=character.role_type,
                damage_score_snapshot=character.damage_score,
                buffer_score_snapshot=character.buffer_score,
                is_treasure_snapshot=character.is_treasure_damage,
                is_fixed_lead_team_buffer_snapshot=character.is_fixed_lead_team_buffer,
                is_group_hunt_snapshot=character.is_group_hunt,
                is_selected=True,
                is_locked=False,
            )
        )
        players.add(character.player_id)
    schedule.preferences.extend(
        SchedulePlayerPreference(
            player_id=player_id,
            allowed_waves=None,
            max_wave_count=None,
            prefer_early=False,
            prefer_contiguous=False,
        )
        for player_id in players
    )
    for wave_no in range(1, wave_count + 1):
        wave = Wave(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            wave_no=wave_no,
            is_locked=False,
            damage_total=0,
            buffer_total=0,
        )
        for template in version.teams:
            team = Team(
                id=uuid.uuid4(),
                schedule_id=schedule.id,
                team_key=template.team_key,
                display_name_snapshot=template.display_name,
                display_color_snapshot=template.display_color,
                display_order_snapshot=template.display_order,
                member_count_snapshot=template.member_count,
                strength_rank_snapshot=template.strength_rank,
                damage_total=0,
                buffer_total=0,
                composition_code="INCOMPLETE",
            )
            team.slots.extend(
                TeamSlot(
                    id=uuid.uuid4(),
                    schedule_id=schedule.id,
                    wave_id=wave.id,
                    team_id=team.id,
                    slot_no=slot_no,
                    is_locked=False,
                )
                for slot_no in range(1, template.member_count + 1)
            )
            wave.teams.append(team)
        schedule.waves.append(wave)
    db.add(schedule)
    db.commit()
    return _load(db, schedule.id)


@router.post("/{schedule_id}/copy/preview", response_model=ScheduleCopyPreview)
def preview_schedule_copy(
    schedule_id: uuid.UUID,
    payload: ScheduleCopyPreviewRequest,
    db: DbSession,
    current_user: ScheduleReader,
) -> ScheduleCopyPreview:
    del current_user
    source = _load(db, schedule_id)
    if source.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": source.revision},
        )
    _target_version, preview = _copy_preview(db, source, payload)
    db.commit()
    return preview


@router.post("/{schedule_id}/copy", response_model=ScheduleDetail, status_code=201)
def copy_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleCopy,
    db: DbSession,
    current_user: ScheduleWriter,
) -> Schedule:
    source = _load(db, schedule_id, for_update=True)
    if source.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": source.revision},
        )
    target_version, preview = _copy_preview(db, source, payload)
    if preview.changes and payload.migration_fingerprint != preview.migration_fingerprint:
        raise AppError(
            409,
            "COPY_PREVIEW_REQUIRED",
            "复制配置已经变化，请重新预览后确认",
        )

    character_ids = {participant.character_id for participant in source.participants}
    characters = list(
        db.scalars(
            select(Character)
            .join(Player, Character.player_id == Player.id)
            .where(Character.id.in_(character_ids))
            .options(selectinload(Character.player))
        )
    )
    character_by_id = {character.id: character for character in characters}
    preference_by_player = {
        preference.player_id: preference for preference in source.preferences
    }
    copied = Schedule(
        id=uuid.uuid4(),
        name=payload.name,
        dungeon_version_id=target_version.id,
        formula_version_id=target_version.formula_version_id,
        wave_count=preview.wave_count,
        status="DRAFT",
        note=source.note,
        revision=1,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    copied_player_ids: set[uuid.UUID] = set()
    for source_participant in source.participants:
        character = character_by_id.get(source_participant.character_id)
        if character is None:
            continue
        is_active = character.is_active and character.player.is_active
        copied.participants.append(
            ScheduleParticipant(
                character_id=character.id,
                player_id_snapshot=character.player_id,
                player_name_snapshot=character.player.display_name,
                character_name_snapshot=character.profession,
                profession_snapshot=character.profession,
                role_type_snapshot=character.role_type,
                damage_score_snapshot=character.damage_score,
                buffer_score_snapshot=character.buffer_score,
                is_treasure_snapshot=character.is_treasure_damage,
                is_fixed_lead_team_buffer_snapshot=character.is_fixed_lead_team_buffer,
                is_group_hunt_snapshot=character.is_group_hunt,
                is_selected=source_participant.is_selected and is_active,
                is_locked=False,
                unassigned_reason=(
                    None
                    if is_active
                    else {"code": "SOURCE_INACTIVE", "message": "角色或玩家已停用"}
                ),
            )
        )
        copied_player_ids.add(character.player_id)
    for player_id in copied_player_ids:
        preference = preference_by_player.get(player_id)
        copied.preferences.append(
            SchedulePlayerPreference(
                player_id=player_id,
                allowed_waves=(
                    [
                        wave_no
                        for wave_no in preference.allowed_waves
                        if wave_no <= preview.wave_count
                    ]
                    if preference is not None and preference.allowed_waves is not None
                    else None
                ),
                max_wave_count=(
                    min(preference.max_wave_count, preview.wave_count)
                    if preference is not None and preference.max_wave_count is not None
                    else None
                ),
                prefer_early=preference.prefer_early if preference is not None else False,
                prefer_contiguous=(
                    preference.prefer_contiguous if preference is not None else False
                ),
            )
        )
    migrate_structure = target_version.id != source.dungeon_version_id
    source_team_templates = source.waves[0].teams
    team_configs: list[tuple[str, str, str, int, int, int | None]]
    if migrate_structure:
        team_configs = [
            (
                template.team_key,
                template.display_name,
                template.display_color,
                template.display_order,
                template.member_count,
                template.strength_rank,
            )
            for template in target_version.teams
        ]
    else:
        team_configs = [
            (
                template.team_key,
                template.display_name_snapshot,
                template.display_color_snapshot,
                template.display_order_snapshot,
                template.member_count_snapshot,
                template.strength_rank_snapshot,
            )
            for template in source_team_templates
        ]
    for wave_no in range(1, preview.wave_count + 1):
        copied_wave = Wave(
            id=uuid.uuid4(),
            schedule_id=copied.id,
            wave_no=wave_no,
            is_locked=False,
            damage_total=0,
            buffer_total=0,
        )
        for (
            team_key,
            display_name,
            display_color,
            display_order,
            member_count,
            rank,
        ) in team_configs:
            copied_team = Team(
                id=uuid.uuid4(),
                schedule_id=copied.id,
                team_key=team_key,
                display_name_snapshot=display_name,
                display_color_snapshot=display_color,
                display_order_snapshot=display_order,
                member_count_snapshot=member_count,
                strength_rank_snapshot=rank,
                damage_total=0,
                buffer_total=0,
                composition_code="INCOMPLETE",
            )
            copied_team.slots.extend(
                TeamSlot(
                    id=uuid.uuid4(),
                    schedule_id=copied.id,
                    wave_id=copied_wave.id,
                    team_id=copied_team.id,
                    slot_no=slot_no,
                    is_locked=False,
                )
                for slot_no in range(
                    1,
                    member_count + 1,
                )
            )
            copied_wave.teams.append(copied_team)
        copied.waves.append(copied_wave)
    if source.active_rule_set is not None:
        copied.rule_sets.append(
            ScheduleRuleSet(
                id=uuid.uuid4(),
                schedule_id=copied.id,
                input_revision=1,
                source_text=source.active_rule_set.source_text,
                source_hash=source.active_rule_set.source_hash,
                context_hash=source.active_rule_set.context_hash,
                status="STALE",
                model_provider="COPIED_SOURCE",
                model_name=source.active_rule_set.model_name,
                provider_response_id=None,
                prompt_version=source.active_rule_set.prompt_version,
                schema_version=source.active_rule_set.schema_version,
                parsed_rules=[],
                resolved_references={},
                issues=[
                    {
                        "code": "RULE_SET_REPARSE_REQUIRED",
                        "candidateId": None,
                        "field": None,
                        "reference": "复制排表后需要基于新的参团快照重新解析",
                        "matches": [],
                    }
                ],
                created_by=current_user.id,
            )
        )
    db.add(copied)
    db.commit()
    return _load(db, copied.id)


@router.get("/{schedule_id}", response_model=ScheduleDetail)
def get_schedule(schedule_id: uuid.UUID, db: DbSession, current_user: ScheduleReader) -> Schedule:
    del current_user
    item = _load(db, schedule_id)
    db.commit()
    return item


@router.post("/{schedule_id}/archive", response_model=ScheduleDetail)
def archive_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleLifecycleRequest,
    db: DbSession,
    current_user: SchedulePublisherEditor,
) -> Schedule:
    item = _load(db, schedule_id, for_update=True)
    if item.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ALREADY_ARCHIVED", "排表已经归档")
    if item.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": item.revision},
        )
    item.status = "ARCHIVED"
    item.revision += 1
    item.updated_by = current_user.id
    item.updated_at = func.now()
    db.commit()
    return _load(db, item.id)


@router.post("/{schedule_id}/restore", response_model=ScheduleDetail)
def restore_archived_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleLifecycleRequest,
    db: DbSession,
    current_user: SchedulePublisherEditor,
) -> Schedule:
    item = _load(db, schedule_id, for_update=True)
    if item.status != "ARCHIVED":
        raise AppError(409, "SCHEDULE_NOT_ARCHIVED", "只有已归档排表可以恢复")
    if item.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": item.revision},
        )
    item.status = "DRAFT"
    item.revision += 1
    item.validation_summary = None
    item.updated_by = current_user.id
    item.updated_at = func.now()
    db.commit()
    return _load(db, item.id)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleDeleteRequest,
    db: DbSession,
    current_user: ScheduleDeleterEditor,
) -> None:
    item = _load(db, schedule_id, for_update=True)
    if item.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": item.revision},
        )
    if item.status != "DRAFT" or item.last_published_version is not None:
        raise AppError(
            409,
            "SCHEDULE_DELETE_NOT_ALLOWED",
            "只有从未发布的草稿排表可以永久删除",
        )
    published_version_count = db.scalar(
        select(func.count()).select_from(ScheduleVersion).where(
            ScheduleVersion.schedule_id == item.id
        )
    ) or 0
    if published_version_count:
        raise AppError(
            409,
            "SCHEDULE_DELETE_NOT_ALLOWED",
            "存在发布历史的排表不能永久删除，请改用归档",
        )
    if payload.confirmation_name != item.name:
        raise AppError(
            422,
            "SCHEDULE_DELETE_CONFIRMATION_MISMATCH",
            "输入的排表名称不匹配",
            path="confirmationName",
        )
    db.execute(delete(Schedule).where(Schedule.id == item.id))
    db.commit()


@router.patch("/{schedule_id}", response_model=ScheduleDetail)
def update_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    db: DbSession,
    current_user: ScheduleEditor,
) -> Schedule:
    item = _load(db, schedule_id)
    new_wave_count = payload.wave_count
    removed_waves: list[Wave] = []
    if new_wave_count is not None and new_wave_count != item.wave_count:
        version = db.get(DungeonVersion, item.dungeon_version_id)
        if version is None:
            raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
        if new_wave_count < version.min_wave_count or (
            version.max_wave_count is not None and new_wave_count > version.max_wave_count
        ):
            raise AppError(422, "WAVE_COUNT_OUT_OF_RANGE", "波数超出副本允许范围")
        positions_per_wave = sum(team.member_count_snapshot for team in item.waves[0].teams)
        if new_wave_count * positions_per_wave > MAX_SCHEDULE_POSITIONS:
            raise AppError(
                422,
                "SCHEDULE_POSITION_LIMIT_EXCEEDED",
                f"排表总位置数不能超过 {MAX_SCHEDULE_POSITIONS}",
            )
        if new_wave_count < item.wave_count:
            removed_waves = [wave for wave in item.waves if wave.wave_no > new_wave_count]
            occupied = [
                wave.wave_no
                for wave in removed_waves
                if wave.is_locked
                or any(
                    slot.is_locked or slot.participant_id
                    for team in wave.teams
                    for slot in team.slots
                )
            ]
            if occupied and not payload.confirm_wave_reduction:
                raise AppError(
                    409,
                    "WAVE_REDUCTION_CONFIRMATION_REQUIRED",
                    "被删除波次包含已分配或锁定位置，需要确认后重试",
                    details={"waveNos": occupied},
                )

    _claim_revision(db, item, payload.base_revision, current_user)
    if payload.name is not None:
        item.name = payload.name
    if "note" in payload.model_fields_set:
        item.note = payload.note.strip() if payload.note else None
    if new_wave_count is not None and new_wave_count != item.wave_count:
        if new_wave_count > item.wave_count:
            team_templates = list(item.waves[0].teams)
            item.waves.extend(
                _new_wave_from_snapshot(item, wave_no, team_templates)
                for wave_no in range(item.wave_count + 1, new_wave_count + 1)
            )
        else:
            for wave in removed_waves:
                item.waves.remove(wave)
            for preference in item.preferences:
                if preference.allowed_waves is not None:
                    preference.allowed_waves = [
                        wave_no
                        for wave_no in preference.allowed_waves
                        if wave_no <= new_wave_count
                    ]
                if (
                    preference.max_wave_count is not None
                    and preference.max_wave_count > new_wave_count
                ):
                    preference.max_wave_count = new_wave_count
        item.wave_count = new_wave_count
        invalidate_active_rule_set(item)
    item.status = "DRAFT"
    item.validation_summary = None
    db.commit()
    return _load(db, item.id)


@router.put("/{schedule_id}/participants", response_model=ScheduleDetail)
def update_schedule_participants(
    schedule_id: uuid.UUID,
    payload: ScheduleParticipantsUpdate,
    db: DbSession,
    current_user: ScheduleEditor,
) -> Schedule:
    item = _load(db, schedule_id)
    participant_by_id = {participant.id: participant for participant in item.participants}
    selected_ids = set(payload.selected_participant_ids)
    selection_changed = selected_ids != {
        participant.id for participant in item.participants if participant.is_selected
    }
    unknown_ids = selected_ids - participant_by_id.keys()
    if unknown_ids:
        raise AppError(
            422,
            "SCHEDULE_PARTICIPANT_NOT_FOUND",
            "部分参团角色不属于当前排表",
            details={"participantIds": sorted(map(str, unknown_ids))},
        )
    _claim_revision(db, item, payload.base_revision, current_user)
    for participant in item.participants:
        participant.is_selected = participant.id in selected_ids
        if not participant.is_selected:
            participant.is_locked = False
    for wave in item.waves:
        for team in wave.teams:
            for slot in team.slots:
                if slot.participant_id is not None and slot.participant_id not in selected_ids:
                    slot.participant_id = None
                    slot.is_locked = False
    if selection_changed:
        invalidate_active_rule_set(item)
    item.status = "DRAFT"
    item.validation_summary = None
    db.commit()
    return _load(db, item.id)


@router.put("/{schedule_id}/player-preferences", response_model=ScheduleDetail)
def update_schedule_preferences(
    schedule_id: uuid.UUID,
    payload: SchedulePreferencesUpdate,
    db: DbSession,
    current_user: ScheduleEditor,
) -> Schedule:
    item = _load(db, schedule_id)
    expected_player_ids = {
        participant.player_id_snapshot for participant in item.participants
    }
    received_player_ids = {preference.player_id for preference in payload.preferences}
    if received_player_ids != expected_player_ids:
        raise AppError(
            422,
            "SCHEDULE_PREFERENCE_PLAYERS_MISMATCH",
            "玩家偏好必须完整覆盖当前排表中的玩家",
            details={
                "missingPlayerIds": sorted(map(str, expected_player_ids - received_player_ids)),
                "unknownPlayerIds": sorted(map(str, received_player_ids - expected_player_ids)),
            },
        )
    for preference_input in payload.preferences:
        if preference_input.allowed_waves is not None and any(
            wave_no > item.wave_count for wave_no in preference_input.allowed_waves
        ):
            raise AppError(422, "ALLOWED_WAVE_OUT_OF_RANGE", "可用波次超出排表范围")
        if (
            preference_input.max_wave_count is not None
            and preference_input.max_wave_count > item.wave_count
        ):
            raise AppError(422, "MAX_WAVE_COUNT_OUT_OF_RANGE", "最大出场次数超出排表波数")

    _claim_revision(db, item, payload.base_revision, current_user)
    preference_by_player = {
        preference.player_id: preference for preference in item.preferences
    }
    rule_context_changed = False
    for preference_input in payload.preferences:
        stored_preference = preference_by_player.get(preference_input.player_id)
        normalized_allowed_waves = (
            sorted(preference_input.allowed_waves)
            if preference_input.allowed_waves is not None
            else None
        )
        if stored_preference is None:
            stored_preference = SchedulePlayerPreference(player_id=preference_input.player_id)
            item.preferences.append(stored_preference)
        stored_allowed_waves = (
            sorted(stored_preference.allowed_waves)
            if stored_preference.allowed_waves is not None
            else None
        )
        if (
            stored_allowed_waves != normalized_allowed_waves
            or stored_preference.max_wave_count != preference_input.max_wave_count
        ):
            rule_context_changed = True
        stored_preference.allowed_waves = normalized_allowed_waves
        stored_preference.max_wave_count = preference_input.max_wave_count
        stored_preference.prefer_early = preference_input.prefer_early
        stored_preference.prefer_contiguous = preference_input.prefer_contiguous
    if rule_context_changed:
        invalidate_active_rule_set(item)
    item.status = "DRAFT"
    item.validation_summary = None
    db.commit()
    return _load(db, item.id)


@router.post("/{schedule_id}/sync-characters/preview", response_model=ScheduleSyncPreview)
def preview_schedule_character_sync(
    schedule_id: uuid.UUID, db: DbSession, current_user: ScheduleReader
) -> ScheduleSyncPreview:
    del current_user
    item = _load(db, schedule_id)
    characters, fingerprint = _sync_source_state(db, item)
    changes = _sync_changes(item, characters)
    summary = {
        action: sum(change.action == action for change in changes)
        for action in ("ADD", "UPDATE", "DESELECT")
    }
    db.commit()
    return ScheduleSyncPreview(
        revision=item.revision,
        source_fingerprint=fingerprint,
        changes=changes,
        summary=summary,
    )


@router.post("/{schedule_id}/sync-characters/commit", response_model=ScheduleDetail)
def commit_schedule_character_sync(
    schedule_id: uuid.UUID,
    payload: ScheduleSyncCommit,
    db: DbSession,
    current_user: ScheduleEditor,
) -> Schedule:
    item = _load(db, schedule_id)
    characters, fingerprint = _sync_source_state(db, item)
    if fingerprint != payload.source_fingerprint:
        raise AppError(
            409,
            "SCHEDULE_SYNC_SOURCE_CHANGED",
            "人员数据在预览后发生变化，请重新预览",
        )
    changes = _sync_changes(item, characters)
    if not changes:
        if item.revision != payload.base_revision:
            raise AppError(
                409,
                "SCHEDULE_REVISION_CONFLICT",
                "排表已被其他操作修改，请刷新后重试",
                details={"expected": payload.base_revision, "current": item.revision},
            )
        db.commit()
        return item
    _claim_revision(db, item, payload.base_revision, current_user)
    character_by_id = {character.id: character for character in characters}
    participant_by_character = {
        participant.character_id: participant for participant in item.participants
    }
    preference_player_ids = {
        preference.player_id for preference in item.preferences
    }
    deselected_participant_ids: set[uuid.UUID] = set()
    for change in changes:
        character = character_by_id[change.character_id]
        participant = participant_by_character.get(change.character_id)
        if change.action == "ADD":
            participant = ScheduleParticipant(
                character_id=character.id,
                player_id_snapshot=character.player_id,
                player_name_snapshot=character.player.display_name,
                character_name_snapshot=character.profession,
                profession_snapshot=character.profession,
                role_type_snapshot=character.role_type,
                damage_score_snapshot=character.damage_score,
                buffer_score_snapshot=character.buffer_score,
                is_treasure_snapshot=character.is_treasure_damage,
                is_fixed_lead_team_buffer_snapshot=character.is_fixed_lead_team_buffer,
                is_group_hunt_snapshot=character.is_group_hunt,
                is_selected=True,
                is_locked=False,
            )
            item.participants.append(participant)
            if character.player_id not in preference_player_ids:
                item.preferences.append(
                    SchedulePlayerPreference(
                        player_id=character.player_id,
                        allowed_waves=None,
                        max_wave_count=None,
                        prefer_early=False,
                        prefer_contiguous=False,
                    )
                )
                preference_player_ids.add(character.player_id)
        elif participant is not None and change.action == "DESELECT":
            participant.is_selected = False
            participant.is_locked = False
            deselected_participant_ids.add(participant.id)
        elif participant is not None and change.action == "UPDATE":
            participant.player_name_snapshot = character.player.display_name
            participant.character_name_snapshot = character.profession
            participant.profession_snapshot = character.profession
            participant.role_type_snapshot = character.role_type
            participant.damage_score_snapshot = character.damage_score
            participant.buffer_score_snapshot = character.buffer_score
            participant.is_treasure_snapshot = character.is_treasure_damage
            participant.is_fixed_lead_team_buffer_snapshot = character.is_fixed_lead_team_buffer
            participant.is_group_hunt_snapshot = character.is_group_hunt
    if deselected_participant_ids:
        for wave in item.waves:
            for team in wave.teams:
                for slot in team.slots:
                    if slot.participant_id in deselected_participant_ids:
                        slot.participant_id = None
                        slot.is_locked = False
    invalidate_active_rule_set(item)
    item.status = "DRAFT"
    item.validation_summary = None
    db.commit()
    return _load(db, item.id)


@router.post("/{schedule_id}/validate", response_model=ValidationReport)
def validate_schedule(
    schedule_id: uuid.UUID,
    payload: ValidationRequest,
    request: Request,
    db: DbSession,
    current_user: ScheduleReader,
) -> ValidationReport:
    item = _load(db, schedule_id)
    if item.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": item.revision},
        )
    if current_user.has_permission("SCHEDULE_WRITE") and item.status != "ARCHIVED":
        enforce_schedule_edit_lock(schedule_id, request, db, current_user)
    version = db.get(DungeonVersion, item.dungeon_version_id)
    if version is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
    composition_rules = CompositionRules.model_validate(version.composition_rules)
    special_role_rules = SpecialRoleRules.model_validate(version.special_role_rules)
    strength_order_rules = StrengthOrderRules.model_validate(version.strength_order_rules)
    teams = [team for wave in item.waves for team in wave.teams]
    capacity = sum(team.member_count_snapshot for team in teams)
    selected = [participant for participant in item.participants if participant.is_selected]
    damage = sum(participant.role_type_snapshot == "DAMAGE" for participant in selected)
    buffers = len(selected) - damage
    issues: list[IssueView] = []
    if len(selected) > capacity:
        issues.append(
            IssueView(
                severity="ERROR",
                code="CAPACITY_EXCEEDED",
                message_params={"capacity": capacity, "current": len(selected)},
            )
        )
    elif len(selected) < capacity:
        issues.append(
            IssueView(
                severity="INFO",
                code="PARTICIPANT_SHORTAGE",
                message_params={
                    "capacity": capacity,
                    "current": len(selected),
                    "shortage": capacity - len(selected),
                },
            )
        )
    required_distinct_players = max(
        (
            sum(team.member_count_snapshot for team in wave.teams)
            for wave in item.waves
        ),
        default=0,
    )
    player_feasibility = distinct_player_feasibility(
        required_distinct_players,
        (participant.player_id_snapshot for participant in selected),
    )
    if not player_feasibility.can_fill_wave:
        issues.append(
            IssueView(
                severity="WARNING",
                code="DISTINCT_PLAYER_SHORTAGE",
                message_params={
                    "required": player_feasibility.required,
                    "current": player_feasibility.current,
                    "shortage": player_feasibility.shortage,
                },
            )
        )
    requirements = composition_role_requirements(
        composition_rules, (team.team_key for team in teams)
    )
    feasibility = composition_feasibility(
        composition_rules,
        (team.team_key for team in teams),
        available_damage=damage,
        available_buffers=buffers,
    )
    if damage < requirements.ideal_damage:
        issues.append(
            IssueView(
                severity="WARNING",
                code="DAMAGE_IDEAL_SHORTAGE",
                message_params={
                    "required": requirements.ideal_damage,
                    "current": damage,
                    "shortage": requirements.ideal_damage - damage,
                },
            )
        )
    if buffers < requirements.base_buffers:
        issues.append(
            IssueView(
                severity="WARNING",
                code="BUFFER_BASE_SHORTAGE",
                message_params={
                    "required": requirements.base_buffers,
                    "current": buffers,
                    "shortage": requirements.base_buffers - buffers,
                },
            )
        )
    if feasibility.can_fill_all_teams and damage < requirements.ideal_damage:
        issues.append(
            IssueView(
                severity="INFO",
                code="FALLBACK_COMPOSITION_FEASIBLE",
                message_params={
                    "damageUsed": feasibility.best_damage_usage,
                    "buffersUsed": feasibility.best_buffer_usage,
                    "strategy": "使用低优先级合法组成补足完整队伍",
                },
            )
        )
    elif not feasibility.can_fill_all_teams:
        issues.append(
            IssueView(
                severity="WARNING",
                code="FULL_COMPOSITION_INFEASIBLE",
                message_params={
                    "damage": damage,
                    "buffers": buffers,
                    "requiredDamage": feasibility.closest_damage_required,
                    "requiredBuffers": feasibility.closest_buffers_required,
                    "damageShortage": feasibility.damage_shortage,
                    "bufferShortage": feasibility.buffer_shortage,
                },
            )
        )
    role_surpluses = (
        ("DAMAGE", damage, feasibility.maximum_damage),
        ("BUFFER", buffers, feasibility.maximum_buffers),
    )
    for role_type, current, maximum in role_surpluses:
        if current > maximum:
            issues.append(
                IssueView(
                    severity="WARNING",
                    code="UNUSABLE_ROLE_SURPLUS",
                    message_params={
                        "roleType": role_type,
                        "current": current,
                        "maximumForFullTeams": maximum,
                        "surplus": current - maximum,
                        "reason": "超过全部完整队伍合法组成可容纳的数量",
                    },
                )
            )
    treasure_required = item.wave_count * sum(
        rule.count_per_wave
        for rule in special_role_rules.rules
        if rule.character_flag == "TREASURE_DAMAGE"
    )
    treasures = sum(
        participant.is_treasure_snapshot and participant.role_type_snapshot == "DAMAGE"
        for participant in selected
    )
    if treasures < treasure_required:
        issues.append(
            IssueView(
                severity="WARNING",
                code="TREASURE_SHORTAGE",
                message_params={
                    "required": treasure_required,
                    "current": treasures,
                    "shortage": treasure_required - treasures,
                },
            )
        )
    if strength_order_rules.orders:
        issues.append(
            IssueView(
                severity="INFO",
                code="STRENGTH_ORDER_CHECK_ON_GENERATION",
                message_params={
                    "ruleCount": len(strength_order_rules.orders),
                    "reason": "空排表尚无队伍分配，生成方案时将校验并报告强度顺序冲突",
                },
            )
        )
    selected_by_player: dict[uuid.UUID, list[ScheduleParticipant]] = {}
    for participant in selected:
        selected_by_player.setdefault(participant.player_id_snapshot, []).append(participant)
    preference_by_player = {
        preference.player_id: preference for preference in item.preferences
    }
    for player_id, player_participants in selected_by_player.items():
        preference = preference_by_player.get(player_id)
        available = item.wave_count
        if preference is not None:
            if preference.allowed_waves is not None:
                available = len(preference.allowed_waves)
            if preference.max_wave_count is not None:
                available = min(available, preference.max_wave_count)
        if len(player_participants) > available:
            issues.append(
                IssueView(
                    severity="WARNING",
                    code="PLAYER_WAVE_CAPACITY_INSUFFICIENT",
                    message_params={
                        "playerId": str(player_id),
                        "playerName": player_participants[0].player_name_snapshot,
                        "selected": len(player_participants),
                        "available": available,
                    },
                )
            )
    summary = {
        "error": sum(issue.severity == "ERROR" for issue in issues),
        "warning": sum(issue.severity == "WARNING" for issue in issues),
        "info": sum(issue.severity == "INFO" for issue in issues),
    }
    report = ValidationReport(revision=item.revision, issues=issues, summary=summary)
    if item.status == "ARCHIVED" or not current_user.has_permission("SCHEDULE_WRITE"):
        return report
    validated_revision = db.scalar(
        update(Schedule)
        .where(Schedule.id == item.id, Schedule.revision == payload.base_revision)
        .values(validation_summary=summary, updated_at=Schedule.updated_at)
        .returning(Schedule.revision)
    )
    if validated_revision is None:
        db.rollback()
        current_revision = db.scalar(select(Schedule.revision).where(Schedule.id == item.id))
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请重新运行预检查",
            details={"expected": payload.base_revision, "current": current_revision},
        )
    db.commit()
    return report
