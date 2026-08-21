import uuid
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession, EditorUser
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.imports import build_error_workbook, build_template, parse_character_workbook
from app.models.imports import ImportBatch, ImportRow
from app.models.personnel import Character, Player
from app.schemas.imports import ImportBatchView

router = APIRouter()


@router.get("/template")
def download_template(current_user: CurrentUser) -> StreamingResponse:
    del current_user
    return _xlsx_response(build_template(), "DNF角色导入模板.xlsx")


@router.post("/preview", response_model=ImportBatchView, status_code=201)
async def preview_import(
    file: Annotated[UploadFile, File()], *, db: DbSession, current_user: EditorUser
) -> ImportBatch:
    settings = get_settings()
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise AppError(422, "IMPORT_FILE_TYPE_INVALID", "只支持 .xlsx 文件")
    content = await file.read(settings.import_max_bytes + 1)
    if len(content) > settings.import_max_bytes:
        raise AppError(413, "IMPORT_FILE_TOO_LARGE", "导入文件超过大小限制")
    try:
        parsed_rows = parse_character_workbook(content, settings.import_max_rows)
    except ValueError as exc:
        raise AppError(422, "IMPORT_WORKBOOK_INVALID", str(exc)) from exc

    players = list(db.scalars(select(Player).options(selectinload(Player.characters))))
    player_by_key = {player.display_name_key: player for player in players}
    summary = {"create": 0, "update": 0, "ignore": 0, "error": 0}
    batch = ImportBatch(
        filename=filename[:255],
        status="PREVIEWED",
        total_rows=len(parsed_rows),
        summary=summary,
        created_by=current_user.id,
        created_at=utc_now(),
    )
    for parsed in parsed_rows:
        action = "ERROR" if parsed.errors else "CREATE"
        player = player_by_key.get(parsed.payload.get("player_key", ""))
        character = None
        if player is not None:
            character = next(
                (
                    item
                    for item in player.characters
                    if item.name_key == parsed.payload.get("character_key")
                ),
                None,
            )
        change_summary = None
        if not parsed.errors and character is not None:
            changes = _changes(character, parsed.payload)
            action = "UPDATE" if changes else "IGNORE"
            change_summary = "、".join(changes) if changes else "无变化"
        summary[action.casefold()] += 1
        batch.rows.append(
            ImportRow(
                row_no=parsed.row_no,
                action=action,
                payload=parsed.payload,
                errors=parsed.errors,
                matched_player_id=player.id if player else None,
                matched_character_id=character.id if character else None,
                change_summary=change_summary,
            )
        )
    batch.summary = summary
    db.add(batch)
    db.commit()
    return _load_batch(db, batch.id)


@router.get("/{batch_id}", response_model=ImportBatchView)
def get_import(batch_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ImportBatch:
    del current_user
    batch = _load_batch(db, batch_id)
    db.commit()
    return batch


@router.post("/{batch_id}/commit", response_model=ImportBatchView)
def commit_import(batch_id: uuid.UUID, db: DbSession, current_user: EditorUser) -> ImportBatch:
    del current_user
    batch = _load_batch(db, batch_id)
    if batch.status != "PREVIEWED":
        raise AppError(409, "IMPORT_ALREADY_COMMITTED", "该导入批次已经确认")
    if any(row.action == "ERROR" for row in batch.rows):
        raise AppError(409, "IMPORT_HAS_ERRORS", "请先修正错误行后重新预览")
    player_cache: dict[str, Player] = {}
    for row in batch.rows:
        if row.action == "IGNORE":
            continue
        payload = row.payload
        player = player_cache.get(payload["player_key"])
        if player is None:
            player = db.scalar(
                select(Player).where(Player.display_name_key == payload["player_key"])
            )
            if player is None:
                player = Player(
                    display_name=payload["player_name"],
                    display_name_key=payload["player_key"],
                    is_active=True,
                )
                db.add(player)
                db.flush()
            player_cache[payload["player_key"]] = player
        character = None
        if row.matched_character_id:
            character = db.get(Character, row.matched_character_id)
        if character is None:
            character = db.scalar(
                select(Character).where(
                    Character.player_id == player.id, Character.name_key == payload["character_key"]
                )
            )
        if character is None:
            character = Character(player_id=player.id)
            db.add(character)
        _apply_payload(character, payload)
    batch.status = "COMMITTED"
    batch.committed_at = utc_now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "IMPORT_DATA_CHANGED", "人员数据已变化，请重新预览") from exc
    return _load_batch(db, batch.id)


@router.get("/{batch_id}/errors.xlsx")
def download_errors(
    batch_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> StreamingResponse:
    del current_user
    batch = _load_batch(db, batch_id)
    rows = [(row.row_no, row.payload, row.errors) for row in batch.rows if row.errors]
    db.commit()
    return _xlsx_response(build_error_workbook(rows), f"{batch_id}-errors.xlsx")


def _load_batch(db: DbSession, batch_id: uuid.UUID) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch)
        .where(ImportBatch.id == batch_id)
        .options(selectinload(ImportBatch.rows))
    )
    if batch is None:
        raise AppError(404, "IMPORT_BATCH_NOT_FOUND", "导入批次不存在")
    return batch


def _changes(character: Character, payload: dict[str, object]) -> list[str]:
    fields = {
        "职业": (character.profession, payload["profession"]),
        "类型": (character.role_type, payload["role_type"]),
        "伤害": (
            str(character.damage_score) if character.damage_score is not None else None,
            payload["damage_score"],
        ),
        "奶评分": (
            str(character.buffer_score) if character.buffer_score is not None else None,
            payload["buffer_score"],
        ),
        "秘宝C": (character.is_treasure_damage, payload["is_treasure_damage"]),
        "默认参团": (character.default_raid_participant, payload["default_raid_participant"]),
        "备注": (character.note, payload["note"]),
    }
    return [name for name, (old, new) in fields.items() if old != new]


def _apply_payload(character: Character, payload: dict[str, object]) -> None:
    character.name = str(payload["character_name"])
    character.name_key = str(payload["character_key"])
    character.profession = str(payload["profession"])
    character.role_type = str(payload["role_type"])
    character.damage_score = payload["damage_score"]  # type: ignore[assignment]
    character.buffer_score = payload["buffer_score"]  # type: ignore[assignment]
    character.is_treasure_damage = bool(payload["is_treasure_damage"])
    character.default_raid_participant = bool(payload["default_raid_participant"])
    character.note = str(payload["note"]) if payload["note"] else None
    character.is_active = True


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
