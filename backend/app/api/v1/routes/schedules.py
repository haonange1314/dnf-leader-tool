import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.models.dungeon import DungeonVersion
from app.models.personnel import Character
from app.models.schedule import (
    Schedule,
    ScheduleParticipant,
    SchedulePlayerPreference,
    Team,
    TeamSlot,
    Wave,
)
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
        .options(selectinload(DungeonVersion.teams))
    )
    if version is None or version.status != "PUBLISHED":
        raise AppError(422, "DUNGEON_VERSION_NOT_PUBLISHED", "只能使用已发布副本版本")
    wave_count = payload.wave_count or version.default_wave_count
    if wave_count < version.min_wave_count or (
        version.max_wave_count is not None and wave_count > version.max_wave_count
    ):
        raise AppError(422, "WAVE_COUNT_OUT_OF_RANGE", "波数超出副本允许范围")
    schedule = Schedule(
        id=uuid.uuid4(),
        name=payload.name.strip(),
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
            .where(Character.is_active.is_(True), Character.default_raid_participant.is_(True))
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
    capacity = sum(team.member_count_snapshot for team in item.waves[0].teams) * item.wave_count
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
    ideal_damage = item.wave_count * sum(
        max(team.member_count_snapshot - 1, 0) for team in item.waves[0].teams
    )
    base_buffers = item.wave_count * len(item.waves[0].teams)
    if damage < ideal_damage:
        issues.append(
            IssueView(
                severity="WARNING",
                code="DAMAGE_IDEAL_SHORTAGE",
                message_params={
                    "required": ideal_damage,
                    "current": damage,
                    "shortage": ideal_damage - damage,
                },
            )
        )
    if buffers < base_buffers:
        issues.append(
            IssueView(
                severity="WARNING",
                code="BUFFER_BASE_SHORTAGE",
                message_params={
                    "required": base_buffers,
                    "current": buffers,
                    "shortage": base_buffers - buffers,
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
