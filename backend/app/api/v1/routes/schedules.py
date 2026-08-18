import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.domain.schedule import MAX_SCHEDULE_POSITIONS, composition_role_requirements
from app.models.dungeon import DungeonVersion
from app.models.personnel import Character, Player
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    SchedulePlayerPreference,
    Team,
    TeamSlot,
    Wave,
)
from app.schemas.dungeon import CompositionRules
from app.schemas.schedule import (
    IssueView,
    ScheduleCreate,
    ScheduleDetail,
    ScheduleList,
    ScheduleSummary,
    ValidationReport,
)

router = APIRouter()


def _load(db: DbSession, schedule_id: uuid.UUID) -> Schedule:
    item = db.scalar(
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(
            selectinload(Schedule.participants),
            selectinload(Schedule.waves).selectinload(Wave.teams).selectinload(Team.slots),
        )
    )
    if item is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    return item


@router.get("", response_model=ScheduleList)
def list_schedules(db: DbSession, current_user: CurrentUser) -> ScheduleList:
    del current_user
    items = list(db.scalars(select(Schedule).order_by(Schedule.updated_at.desc())))
    db.commit()
    return ScheduleList(
        items=[ScheduleSummary.model_validate(item) for item in items], total=len(items)
    )


@router.post("", response_model=ScheduleDetail, status_code=201)
def create_schedule(payload: ScheduleCreate, db: DbSession, current_user: CurrentUser) -> Schedule:
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
                character_name_snapshot=character.name,
                profession_snapshot=character.profession,
                role_type_snapshot=character.role_type,
                damage_score_snapshot=character.damage_score,
                buffer_score_snapshot=character.buffer_score,
                is_treasure_snapshot=character.is_treasure_damage,
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


@router.get("/{schedule_id}", response_model=ScheduleDetail)
def get_schedule(schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Schedule:
    del current_user
    item = _load(db, schedule_id)
    db.commit()
    return item


@router.post("/{schedule_id}/validate", response_model=ValidationReport)
def validate_schedule(
    schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ValidationReport:
    del current_user
    item = _load(db, schedule_id)
    version = db.get(DungeonVersion, item.dungeon_version_id)
    if version is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
    composition_rules = CompositionRules.model_validate(version.composition_rules)
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
    requirements = composition_role_requirements(
        composition_rules, (team.team_key for team in teams)
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
    summary = {
        "error": sum(issue.severity == "ERROR" for issue in issues),
        "warning": sum(issue.severity == "WARNING" for issue in issues),
        "info": sum(issue.severity == "INFO" for issue in issues),
    }
    item.validation_summary = summary
    db.commit()
    return ValidationReport(revision=item.revision, issues=issues, summary=summary)
