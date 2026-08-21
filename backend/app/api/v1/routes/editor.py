import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, ScheduleEditor
from app.application.schedule_editor import apply_schedule_operations
from app.core.errors import AppError
from app.core.security import utc_now
from app.models.dungeon import DungeonVersion
from app.models.schedule import Schedule, ScheduleEditOperation, Team, Wave
from app.schemas.schedule import (
    ScheduleCommandRequest,
    ScheduleCommandResponse,
    ScheduleDetail,
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
        )
    )
    if for_update:
        statement = statement.with_for_update()
    schedule = db.scalar(statement)
    if schedule is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    return schedule


@router.post("/schedules/{schedule_id}/commands", response_model=ScheduleCommandResponse)
def apply_commands(
    schedule_id: uuid.UUID,
    payload: ScheduleCommandRequest,
    db: DbSession,
    current_user: ScheduleEditor,
) -> ScheduleCommandResponse:
    existing = db.get(ScheduleEditOperation, payload.operation_id)
    if existing is not None:
        if existing.schedule_id != schedule_id:
            raise AppError(409, "OPERATION_ID_REUSED", "operationId 已用于其他排表")
        return ScheduleCommandResponse.model_validate(existing.response)
    schedule = _load(db, schedule_id, for_update=True)
    existing = db.get(ScheduleEditOperation, payload.operation_id)
    if existing is not None:
        if existing.schedule_id != schedule_id:
            raise AppError(409, "OPERATION_ID_REUSED", "operationId 已用于其他排表")
        return ScheduleCommandResponse.model_validate(existing.response)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能编辑")
    if schedule.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": schedule.revision},
        )
    version = db.get(DungeonVersion, schedule.dungeon_version_id)
    if version is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
    inverse_operations = apply_schedule_operations(
        db, schedule, version, payload.operations
    )
    schedule.revision += 1
    schedule.status = "DRAFT"
    schedule.validation_summary = None
    schedule.updated_by = current_user.id
    schedule.updated_at = utc_now()
    db.flush()
    response = ScheduleCommandResponse(
        operation_id=payload.operation_id,
        revision=schedule.revision,
        schedule=ScheduleDetail.model_validate(schedule),
        inverse_operations=inverse_operations,
    )
    db.add(
        ScheduleEditOperation(
            id=payload.operation_id,
            schedule_id=schedule.id,
            input_revision=payload.base_revision,
            result_revision=schedule.revision,
            response=response.model_dump(mode="json", by_alias=True),
            created_by=current_user.id,
        )
    )
    db.commit()
    return response
