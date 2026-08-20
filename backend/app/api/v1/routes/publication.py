from __future__ import annotations

import hashlib
import io
import secrets
import uuid
from datetime import timedelta
from typing import Any, cast
from xml.sax.saxutils import escape

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.application.schedule_editor import recompute_schedule
from app.application.schedule_publication import (
    SNAPSHOT_SCHEMA_VERSION,
    create_schedule_snapshot,
    publication_issues,
    restore_snapshot,
)
from app.core.errors import AppError
from app.core.security import utc_now
from app.models.dungeon import DungeonVersion
from app.models.schedule import Schedule, ScheduleVersion, ShareLink, Team, Wave
from app.schemas.schedule import (
    PublicScheduleVersion,
    ScheduleDetail,
    SchedulePublishRequest,
    SchedulePublishResponse,
    ScheduleRestoreRequest,
    ScheduleVersionList,
    ScheduleVersionSummary,
    ScheduleVersionView,
    ShareLinkCreate,
    ShareLinkCreated,
)

router = APIRouter()


def _load_schedule(db: DbSession, schedule_id: uuid.UUID, *, for_update: bool = False) -> Schedule:
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


@router.post("/schedules/{schedule_id}/publish", response_model=SchedulePublishResponse)
def publish_schedule(
    schedule_id: uuid.UUID,
    payload: SchedulePublishRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SchedulePublishResponse:
    schedule = _load_schedule(db, schedule_id, for_update=True)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能发布")
    if schedule.status == "PUBLISHED":
        raise AppError(409, "SCHEDULE_ALREADY_PUBLISHED", "当前排表已经发布且没有新修改")
    if schedule.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": schedule.revision},
        )
    version_definition = db.get(DungeonVersion, schedule.dungeon_version_id)
    if version_definition is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
    recompute_schedule(schedule, version_definition)
    issues = publication_issues(schedule, version_definition)
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    warnings = [issue for issue in issues if issue.severity == "WARNING"]
    if errors:
        raise AppError(
            422,
            "SCHEDULE_NOT_PUBLISHABLE",
            "排表存在结构错误，暂时不能发布",
            details={"issues": [issue.model_dump() for issue in errors]},
        )
    if warnings and not payload.confirm_warnings:
        raise AppError(
            409,
            "PUBLISH_WARNINGS_NOT_CONFIRMED",
            "排表存在警告，请确认后发布",
            details={"issues": [issue.model_dump() for issue in warnings]},
        )
    snapshot, snapshot_hash = create_schedule_snapshot(schedule)
    version_no = (
        db.scalar(
            select(func.coalesce(func.max(ScheduleVersion.version_no), 0)).where(
                ScheduleVersion.schedule_id == schedule.id
            )
        )
        or 0
    ) + 1
    published = ScheduleVersion(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        version_no=version_no,
        source_revision=schedule.revision,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        formula_version_id=schedule.formula_version_id,
        published_by=current_user.id,
    )
    db.add(published)
    schedule.status = "PUBLISHED"
    schedule.last_published_version = version_no
    schedule.revision += 1
    schedule.updated_by = current_user.id
    schedule.updated_at = utc_now()
    db.commit()
    refreshed = _load_schedule(db, schedule.id)
    return SchedulePublishResponse(
        version=ScheduleVersionView.model_validate(published),
        schedule=ScheduleDetail.model_validate(refreshed),
        issues=issues,
    )


@router.get("/schedules/{schedule_id}/versions", response_model=ScheduleVersionList)
def list_schedule_versions(
    schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ScheduleVersionList:
    del current_user
    if db.get(Schedule, schedule_id) is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    versions = list(
        db.scalars(
            select(ScheduleVersion)
            .where(ScheduleVersion.schedule_id == schedule_id)
            .order_by(ScheduleVersion.version_no.desc())
        )
    )
    return ScheduleVersionList(
        items=[ScheduleVersionSummary.model_validate(version) for version in versions],
        total=len(versions),
    )


@router.get(
    "/schedules/{schedule_id}/versions/{version_no}", response_model=ScheduleVersionView
)
def get_schedule_version(
    schedule_id: uuid.UUID,
    version_no: int,
    db: DbSession,
    current_user: CurrentUser,
) -> ScheduleVersionView:
    del current_user
    version = db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.schedule_id == schedule_id,
            ScheduleVersion.version_no == version_no,
        )
    )
    if version is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    return ScheduleVersionView.model_validate(version)


@router.post(
    "/schedules/{schedule_id}/versions/{version_no}/restore-as-draft",
    response_model=ScheduleDetail,
)
def restore_schedule_version(
    schedule_id: uuid.UUID,
    version_no: int,
    payload: ScheduleRestoreRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ScheduleDetail:
    schedule = _load_schedule(db, schedule_id, for_update=True)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能恢复版本")
    if schedule.revision != payload.base_revision:
        raise AppError(409, "SCHEDULE_REVISION_CONFLICT", "排表已变化，请刷新后重试")
    version = db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.schedule_id == schedule.id,
            ScheduleVersion.version_no == version_no,
        )
    )
    if version is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    try:
        restore_snapshot(db, schedule, version.snapshot)
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(409, "SCHEDULE_SNAPSHOT_INVALID", "发布版本快照无法恢复") from exc
    schedule.formula_version_id = version.formula_version_id
    schedule.status = "DRAFT"
    schedule.revision += 1
    schedule.validation_summary = None
    schedule.updated_by = current_user.id
    schedule.updated_at = utc_now()
    db.commit()
    return ScheduleDetail.model_validate(_load_schedule(db, schedule.id))


@router.post(
    "/schedule-versions/{version_id}/share-links",
    response_model=ShareLinkCreated,
    status_code=201,
)
def create_share_link(
    version_id: uuid.UUID,
    payload: ShareLinkCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ShareLinkCreated:
    if db.get(ScheduleVersion, version_id) is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    token = secrets.token_urlsafe(32)
    expires_at = (
        utc_now() + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days is not None
        else None
    )
    link = ShareLink(
        id=uuid.uuid4(),
        schedule_version_id=version_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=expires_at,
        created_by=current_user.id,
    )
    db.add(link)
    db.commit()
    return ShareLinkCreated(
        id=link.id,
        schedule_version_id=version_id,
        token=token,
        expires_at=expires_at,
    )


@router.delete("/share-links/{share_link_id}", status_code=204)
def revoke_share_link(
    share_link_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    del current_user
    link = db.get(ShareLink, share_link_id)
    if link is None:
        raise AppError(404, "SHARE_LINK_NOT_FOUND", "分享链接不存在")
    link.revoked_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.get("/share/{token}", response_model=PublicScheduleVersion)
def get_public_schedule(token: str, db: DbSession) -> PublicScheduleVersion:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    link = db.scalar(
        select(ShareLink)
        .where(ShareLink.token_hash == token_hash)
        .options(selectinload(ShareLink.schedule_version))
    )
    now = utc_now()
    if (
        link is None
        or link.revoked_at is not None
        or (link.expires_at is not None and link.expires_at <= now)
    ):
        raise AppError(404, "SHARE_LINK_INVALID", "分享链接无效或已过期")
    version = link.schedule_version
    return PublicScheduleVersion(
        version_id=version.id,
        version_no=version.version_no,
        published_at=version.published_at,
        snapshot=version.snapshot,
    )


@router.get("/schedule-versions/{version_id}/exports/text")
def export_schedule_text(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    del current_user
    version = _version(db, version_id)
    return Response(
        content=_snapshot_text(version.snapshot, version.version_no),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-v{version.version_no}.txt"'
        },
    )


@router.get("/schedule-versions/{version_id}/exports/excel")
def export_schedule_excel(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    del current_user
    version = _version(db, version_id)
    workbook = Workbook()
    sheet = cast(Worksheet, workbook.active)
    sheet.title = "排表"
    sheet.append([version.snapshot.get("name", "排表"), f"发布版本 v{version.version_no}"])
    sheet.append(["波次", "队伍", "位置", "玩家", "角色", "职业", "类型", "评分", "核心"])
    participants = {
        str(item["id"]): item for item in version.snapshot.get("participants", [])
    }
    for wave in version.snapshot.get("waves", []):
        cores = {
            str(item["participantId"]) for item in wave.get("specialAssignments", [])
        }
        for team in wave.get("teams", []):
            for slot in team.get("slots", []):
                participant = participants.get(str(slot.get("participantId")), {})
                score = participant.get("damageScoreSnapshot") or participant.get(
                    "bufferScoreSnapshot"
                )
                sheet.append(
                    [
                        wave["waveNo"],
                        team["displayNameSnapshot"],
                        slot["slotNo"],
                        participant.get("playerNameSnapshot", "待补"),
                        participant.get("characterNameSnapshot", ""),
                        participant.get("professionSnapshot", ""),
                        participant.get("roleTypeSnapshot", ""),
                        score or "",
                        "是" if str(participant.get("id")) in cores else "",
                    ]
                )
    for column_letter in "ABCDEFGHI":
        sheet.column_dimensions[column_letter].width = 18
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-v{version.version_no}.xlsx"'
        },
    )


@router.get("/schedule-versions/{version_id}/exports/image")
def export_schedule_image(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    del current_user
    version = _version(db, version_id)
    lines = _snapshot_text(version.snapshot, version.version_no).splitlines()
    width = 1200
    line_height = 30
    height = max(180, 80 + len(lines) * line_height)
    text_nodes = "".join(
        f'<text x="40" y="{60 + index * line_height}" class="line">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#f7f4ee"/>'
        '<style>.line{font:20px sans-serif;fill:#292724}</style>'
        f"{text_nodes}</svg>"
    )
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-v{version.version_no}.svg"'
        },
    )


def _version(db: DbSession, version_id: uuid.UUID) -> ScheduleVersion:
    version = db.get(ScheduleVersion, version_id)
    if version is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    return version


def _snapshot_text(snapshot: dict[str, Any], version_no: int) -> str:
    lines = [f"{snapshot.get('name', '排表')} · 发布版本 v{version_no}"]
    participants = {str(item["id"]): item for item in snapshot.get("participants", [])}
    for wave in snapshot.get("waves", []):
        lines.append("")
        lines.append(f"第 {wave['waveNo']} 波")
        cores = {str(item["participantId"]) for item in wave.get("specialAssignments", [])}
        for team in wave.get("teams", []):
            members: list[str] = []
            for slot in team.get("slots", []):
                participant = participants.get(str(slot.get("participantId")))
                if participant is None:
                    members.append("待补")
                else:
                    core = "【核心】" if str(participant["id"]) in cores else ""
                    members.append(
                        f"{participant['playerNameSnapshot']}·{participant['characterNameSnapshot']}{core}"
                    )
            lines.append(f"{team['displayNameSnapshot']}：{' / '.join(members)}")
    return "\n".join(lines)
