from fastapi import APIRouter
from sqlalchemy import func, select, text, update

from app.api.dependencies import BufferConversionReader, BufferConversionWriter, DbSession
from app.domain.scoring.buffer_conversion import calculate_actual_buffer_score
from app.models.buffer_conversion import BufferConversionVersion
from app.schemas.buffer_conversion import (
    BufferConversionPreview,
    BufferConversionPreviewResult,
    BufferConversionVersionCreate,
    BufferConversionVersionList,
    BufferConversionVersionView,
)

router = APIRouter(prefix="/buffer-conversions")


def _latest(db: DbSession) -> BufferConversionVersion:
    version = db.scalar(
        select(BufferConversionVersion)
        .where(BufferConversionVersion.is_active.is_(True))
        .order_by(BufferConversionVersion.version.desc())
        .limit(1)
    )
    if version is None:  # pragma: no cover - migration always seeds v1
        raise RuntimeError("奶量换算配置未初始化")
    return version


@router.get("/current", response_model=BufferConversionVersionView)
def get_current(db: DbSession, current_user: BufferConversionReader) -> BufferConversionVersion:
    del current_user
    return _latest(db)


@router.get("/versions", response_model=BufferConversionVersionList)
def list_versions(
    db: DbSession, current_user: BufferConversionReader
) -> BufferConversionVersionList:
    del current_user
    items = list(
        db.scalars(
            select(BufferConversionVersion).order_by(BufferConversionVersion.version.desc())
        )
    )
    return BufferConversionVersionList(
        items=[BufferConversionVersionView.model_validate(item) for item in items],
        total=len(items),
    )


@router.post("/versions", response_model=BufferConversionVersionView, status_code=201)
def create_version(
    payload: BufferConversionVersionCreate,
    db: DbSession,
    current_user: BufferConversionWriter,
) -> BufferConversionVersion:
    db.execute(text("LOCK TABLE buffer_conversion_versions IN EXCLUSIVE MODE"))
    next_version = (db.scalar(select(func.max(BufferConversionVersion.version))) or 0) + 1
    db.execute(update(BufferConversionVersion).values(is_active=False))
    version = BufferConversionVersion(
        version=next_version,
        rules=[
            {"profession": rule.profession.strip(), "multiplier": str(rule.multiplier)}
            for rule in payload.rules
        ],
        is_active=True,
        created_by=current_user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.post("/preview", response_model=BufferConversionPreviewResult)
def preview(
    payload: BufferConversionPreview,
    db: DbSession,
    current_user: BufferConversionReader,
) -> BufferConversionPreviewResult:
    del current_user
    version = _latest(db)
    return BufferConversionPreviewResult(
        actual_score=calculate_actual_buffer_score(
            payload.standing_score, payload.profession, version.rules
        )
    )
