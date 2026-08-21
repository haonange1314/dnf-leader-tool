from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession, EditorUser, ScheduleEditor
from app.application.schedule_editor import recompute_schedule
from app.application.schedule_exports import snapshot_png, snapshot_text, snapshot_workbook
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
    SchedulePublicationCheck,
    SchedulePublishRequest,
    SchedulePublishResponse,
    ScheduleRestoreRequest,
    ScheduleVersionCopyRequest,
    ScheduleVersionList,
    ScheduleVersionSummary,
    ScheduleVersionView,
    ShareLinkCreate,
    ShareLinkCreated,
    ShareLinkList,
    ShareLinkView,
    ValidationRequest,
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


def _load_dungeon_version(db: DbSession, version_id: uuid.UUID) -> DungeonVersion:
    version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == version_id)
        .options(
            selectinload(DungeonVersion.dungeon),
            selectinload(DungeonVersion.formula_version),
            selectinload(DungeonVersion.teams),
        )
    )
    if version is None:
        raise AppError(409, "DUNGEON_VERSION_MISSING", "排表引用的副本版本不存在")
    return version


@router.post(
    "/schedules/{schedule_id}/publication-check", response_model=SchedulePublicationCheck
)
def check_schedule_publication(
    schedule_id: uuid.UUID,
    payload: ValidationRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SchedulePublicationCheck:
    del current_user
    schedule = _load_schedule(db, schedule_id)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能发布")
    if schedule.revision != payload.base_revision:
        raise AppError(409, "SCHEDULE_REVISION_CONFLICT", "排表已变化，请刷新后重试")
    version_definition = _load_dungeon_version(db, schedule.dungeon_version_id)
    recompute_schedule(schedule, version_definition)
    issues = publication_issues(schedule, version_definition)
    summary = {
        severity.lower(): sum(issue.severity == severity for issue in issues)
        for severity in ("ERROR", "WARNING", "INFO")
    }
    return SchedulePublicationCheck(
        revision=schedule.revision,
        publishable=summary["error"] == 0,
        issues=issues,
        summary=summary,
    )


@router.post("/schedules/{schedule_id}/publish", response_model=SchedulePublishResponse)
def publish_schedule(
    schedule_id: uuid.UUID,
    payload: SchedulePublishRequest,
    db: DbSession,
    current_user: ScheduleEditor,
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
    version_definition = _load_dungeon_version(db, schedule.dungeon_version_id)
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
    published_at = utc_now()
    snapshot, snapshot_hash = create_schedule_snapshot(
        schedule, version_definition, issues, published_at
    )
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
        published_at=published_at,
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
    current_user: ScheduleEditor,
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
    "/schedules/{schedule_id}/versions/{version_no}/copy-as-draft",
    response_model=ScheduleDetail,
    status_code=201,
)
def copy_schedule_version_as_draft(
    schedule_id: uuid.UUID,
    version_no: int,
    payload: ScheduleVersionCopyRequest,
    db: DbSession,
    current_user: EditorUser,
) -> ScheduleDetail:
    version = db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.schedule_id == schedule_id,
            ScheduleVersion.version_no == version_no,
        )
    )
    if version is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    snapshot = version.snapshot
    copied = Schedule(
        id=uuid.uuid4(),
        name=payload.name,
        dungeon_version_id=uuid.UUID(str(snapshot["dungeonVersionId"])),
        formula_version_id=version.formula_version_id,
        wave_count=int(str(snapshot["waveCount"])),
        status="DRAFT",
        note=str(snapshot["note"]) if snapshot.get("note") is not None else None,
        revision=1,
        validation_summary=None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(copied)
    db.flush()
    try:
        restore_snapshot(db, copied, snapshot)
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(409, "SCHEDULE_SNAPSHOT_INVALID", "发布版本快照无法复制") from exc
    copied.name = payload.name
    copied.status = "DRAFT"
    copied.revision = 1
    copied.last_published_version = None
    copied.validation_summary = None
    db.commit()
    return ScheduleDetail.model_validate(_load_schedule(db, copied.id))


@router.post(
    "/schedule-versions/{version_id}/share-links",
    response_model=ShareLinkCreated,
    status_code=201,
)
def create_share_link(
    version_id: uuid.UUID,
    payload: ShareLinkCreate,
    db: DbSession,
    current_user: EditorUser,
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


@router.get(
    "/schedule-versions/{version_id}/share-links",
    response_model=ShareLinkList,
)
def list_share_links(
    version_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ShareLinkList:
    del current_user
    if db.get(ScheduleVersion, version_id) is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    links = list(
        db.scalars(
            select(ShareLink)
            .where(ShareLink.schedule_version_id == version_id)
            .order_by(ShareLink.created_at.desc())
        )
    )
    now = utc_now()
    items = []
    for link in links:
        status: Literal["ACTIVE", "EXPIRED", "REVOKED"] = (
            "REVOKED"
            if link.revoked_at is not None
            else "EXPIRED"
            if link.expires_at is not None and link.expires_at <= now
            else "ACTIVE"
        )
        items.append(
            ShareLinkView(
                id=link.id,
                schedule_version_id=link.schedule_version_id,
                expires_at=link.expires_at,
                revoked_at=link.revoked_at,
                created_at=link.created_at,
                status=status,
            )
        )
    return ShareLinkList(items=items, total=len(items))


@router.delete("/share-links/{share_link_id}", status_code=204)
def revoke_share_link(
    share_link_id: uuid.UUID, db: DbSession, current_user: EditorUser
) -> Response:
    link = db.get(ShareLink, share_link_id)
    if link is None:
        raise AppError(404, "SHARE_LINK_NOT_FOUND", "分享链接不存在")
    if current_user.role != "OWNER" and link.created_by != current_user.id:
        raise AppError(403, "PERMISSION_DENIED", "只能撤销自己创建的分享链接")
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
        content=snapshot_text(version.snapshot, f"发布版本 v{version.version_no}"),
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
    output = snapshot_workbook(version.snapshot, f"发布版本 v{version.version_no}")
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
) -> StreamingResponse:
    del current_user
    version = _version(db, version_id)
    return StreamingResponse(
        snapshot_png(version.snapshot, f"发布版本 v{version.version_no}"),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-v{version.version_no}.png"'
        },
    )


@router.get("/schedules/{schedule_id}/exports/text")
def export_draft_text(
    schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    del current_user
    schedule, snapshot = _draft_snapshot(db, schedule_id)
    return Response(
        content=snapshot_text(snapshot, f"revision {schedule.revision}", draft=True),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-draft-r{schedule.revision}.txt"'
        },
    )


@router.get("/schedules/{schedule_id}/exports/excel")
def export_draft_excel(
    schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    del current_user
    schedule, snapshot = _draft_snapshot(db, schedule_id)
    output = snapshot_workbook(snapshot, f"revision {schedule.revision}", draft=True)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="schedule-draft-r{schedule.revision}.xlsx"'
            )
        },
    )


@router.get("/schedules/{schedule_id}/exports/image")
def export_draft_image(
    schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    del current_user
    schedule, snapshot = _draft_snapshot(db, schedule_id)
    return StreamingResponse(
        snapshot_png(snapshot, f"revision {schedule.revision}", draft=True),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-draft-r{schedule.revision}.png"'
        },
    )


def _version(db: DbSession, version_id: uuid.UUID) -> ScheduleVersion:
    version = db.get(ScheduleVersion, version_id)
    if version is None:
        raise AppError(404, "SCHEDULE_VERSION_NOT_FOUND", "排表发布版本不存在")
    return version


def _draft_snapshot(db: DbSession, schedule_id: uuid.UUID) -> tuple[Schedule, dict[str, Any]]:
    schedule = _load_schedule(db, schedule_id)
    if schedule.status != "DRAFT":
        raise AppError(409, "SCHEDULE_NOT_DRAFT", "当前排表不是草稿，请从发布历史导出")
    version_definition = _load_dungeon_version(db, schedule.dungeon_version_id)
    recompute_schedule(schedule, version_definition)
    issues = publication_issues(schedule, version_definition)
    snapshot = ScheduleDetail.model_validate(schedule).model_dump(mode="json", by_alias=True)
    snapshot["issues"] = [issue.model_dump(mode="json") for issue in issues]
    return schedule, snapshot
