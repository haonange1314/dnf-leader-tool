import uuid
from collections.abc import Iterable
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, RosterImporter, RosterReader
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.domain.personnel import normalize_key
from app.imports import (
    CharacterExportRow,
    CharacterImportDefaults,
    build_error_workbook,
    build_roster_workbook,
    build_template,
    parse_character_workbook,
)
from app.models.imports import ImportBatch, ImportRow
from app.models.personnel import Character, Player
from app.schemas.imports import ImportBatchListView, ImportBatchSummaryView, ImportBatchView

router = APIRouter()


def _character_import_defaults() -> CharacterImportDefaults:
    settings = get_settings()
    return CharacterImportDefaults(
        is_treasure_damage=settings.import_default_treasure_damage,
        is_fixed_lead_team_buffer=settings.import_default_fixed_lead_team_buffer,
        is_group_hunt=settings.import_default_group_hunt,
        default_raid_participant=settings.import_default_raid_participant,
    )


@router.get("/template")
def download_template(current_user: RosterReader) -> StreamingResponse:
    del current_user
    return _xlsx_response(
        build_template(_character_import_defaults()), "DNF角色导入模板.xlsx"
    )


@router.get("/export.xlsx")
def download_current_roster(db: DbSession, current_user: RosterReader) -> StreamingResponse:
    del current_user
    players = list(
        db.scalars(
            select(Player)
            .where(Player.is_active.is_(True))
            .options(selectinload(Player.characters))
            .order_by(Player.sort_order, Player.display_name_key, Player.id)
        ).unique()
    )
    rows = [
        CharacterExportRow(
            player_name=player.display_name,
            profession=character.profession,
            role_type=character.role_type,
            damage_score=character.damage_score,
            buffer_score=character.buffer_score,
            is_treasure_damage=character.is_treasure_damage,
            is_fixed_lead_team_buffer=character.is_fixed_lead_team_buffer,
            is_group_hunt=character.is_group_hunt,
            default_raid_participant=character.default_raid_participant,
        )
        for player in players
        for character in player.characters
        if character.is_active
    ]
    db.commit()
    try:
        content = build_roster_workbook(rows, _character_import_defaults())
    except ValueError as exc:
        raise AppError(409, "ROSTER_EXPORT_INVALID", str(exc)) from exc
    return _xlsx_response(content, "DNF当前人员表.xlsx")


@router.get("/history", response_model=ImportBatchListView)
def list_import_history(
    db: DbSession,
    current_user: RosterImporter,
    limit: int = 20,
    offset: int = 0,
) -> ImportBatchListView:
    del current_user
    safe_limit = min(max(limit, 1), 100)
    safe_offset = max(offset, 0)
    total = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    batches = list(
        db.scalars(
            select(ImportBatch)
            .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
            .limit(safe_limit)
            .offset(safe_offset)
        )
    )
    db.commit()
    return ImportBatchListView(
        items=[ImportBatchSummaryView.model_validate(batch) for batch in batches],
        total=total,
    )


@router.post("/preview", response_model=ImportBatchView, status_code=201)
async def preview_import(
    file: Annotated[UploadFile, File()], *, db: DbSession, current_user: RosterImporter
) -> ImportBatch:
    settings = get_settings()
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise AppError(422, "IMPORT_FILE_TYPE_INVALID", "只支持 .xlsx 文件")
    content = await file.read(settings.import_max_bytes + 1)
    if len(content) > settings.import_max_bytes:
        raise AppError(413, "IMPORT_FILE_TOO_LARGE", "导入文件超过大小限制")
    try:
        parsed_rows = parse_character_workbook(
            content,
            settings.import_max_rows,
            _character_import_defaults(),
        )
    except ValueError as exc:
        raise AppError(422, "IMPORT_WORKBOOK_INVALID", str(exc)) from exc

    players = list(
        db.scalars(
            select(Player)
            .options(selectinload(Player.characters))
            .order_by(Player.sort_order, Player.display_name_key, Player.id)
        )
    )
    player_by_key = {player.display_name_key: player for player in players}
    reactivating_player_keys: set[str] = set()
    new_player_keys: set[str] = set()
    change_details: list[dict[str, object]] = []
    summary = {
        "create": 0,
        "update": 0,
        "ignore": 0,
        "deactivate": 0,
        "deactivate_players": 0,
        "reactivate_players": 0,
        "reorder": 0,
        "error": 0,
        "sync": 1,
        "deactivation_fingerprint": 0,
    }
    batch = ImportBatch(
        filename=filename[:255],
        status="PREVIEWED",
        total_rows=len(parsed_rows),
        summary=summary,
        created_by=current_user.id,
        created_at=utc_now(),
    )
    for parsed in parsed_rows:
        action = "CREATE"
        player = player_by_key.get(parsed.payload.get("player_key", ""))
        character = None
        if player is not None:
            matches = _profession_matches(player.characters, parsed.payload)
            if len(matches) > 1:
                parsed.errors.append(
                    {
                        "code": "AMBIGUOUS_CHARACTER",
                        "message": "该玩家下存在多个相同职业，无法自动匹配",
                    }
                )
            elif matches:
                character = matches[0]
        change_summary = None
        reactivate_player = False
        if not parsed.errors and player is not None and not player.is_active:
            player_key = str(parsed.payload["player_key"])
            if player_key not in reactivating_player_keys:
                reactivating_player_keys.add(player_key)
                summary["reactivate_players"] += 1
                reactivate_player = True
        if parsed.errors:
            action = "ERROR"
        elif character is not None:
            changes = _changes(character, parsed.payload)
            if reactivate_player:
                changes.insert(0, "玩家状态")
            action = "UPDATE" if changes else "IGNORE"
            change_summary = "、".join(changes) if changes else "无变化"
        elif player is None:
            player_key = str(parsed.payload["player_key"])
            fields = ["新增角色"]
            if player_key not in new_player_keys:
                fields.insert(0, "新增玩家")
                new_player_keys.add(player_key)
            change_summary = "、".join(fields)
        elif character is None:
            fields = ["新增角色"]
            if reactivate_player:
                fields.insert(0, "恢复玩家")
            change_summary = "、".join(fields)
        summary[action.casefold()] += 1
        if action in {"CREATE", "UPDATE"}:
            change_details.append(
                {
                    "action": "REACTIVATE" if reactivate_player else action,
                    "player_name": str(parsed.payload.get("player_name", "")),
                    "profession": str(parsed.payload.get("profession", "")) or None,
                    "row_no": parsed.row_no,
                    "fields": (change_summary or "").split("、"),
                }
            )
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
    if summary["error"] == 0:
        imported_professions = _imported_professions(
            row.payload for row in batch.rows
        )
        missing_players, missing_characters = _active_records_missing_from_import(
            players, imported_professions
        )
        summary["deactivate"] = len(missing_characters)
        summary["deactivate_players"] = len(missing_players)
        summary["deactivation_fingerprint"] = _deactivation_fingerprint(
            missing_players, missing_characters
        )
        change_details.extend(
            {
                "action": "DEACTIVATE_PLAYER",
                "player_name": player.display_name,
                "profession": None,
                "row_no": None,
                "fields": ["停用玩家"],
            }
            for player in missing_players
        )
        change_details.extend(
            {
                "action": "DEACTIVATE_CHARACTER",
                "player_name": character.player.display_name,
                "profession": character.profession,
                "row_no": None,
                "fields": ["停用角色"],
            }
            for character in missing_characters
        )
        ordering_changes = _ordering_change_details(players, batch.rows)
        summary["reorder"] = len(ordering_changes)
        change_details.extend(ordering_changes)
    batch.summary = summary
    batch.change_details = change_details
    db.add(batch)
    db.commit()
    return _load_batch(db, batch.id)


@router.get("/{batch_id}", response_model=ImportBatchView)
def get_import(batch_id: uuid.UUID, db: DbSession, current_user: RosterImporter) -> ImportBatch:
    del current_user
    batch = _load_batch(db, batch_id)
    db.commit()
    return batch


@router.post("/{batch_id}/commit", response_model=ImportBatchView)
def commit_import(batch_id: uuid.UUID, db: DbSession, current_user: RosterImporter) -> ImportBatch:
    del current_user
    batch = _load_batch(db, batch_id)
    if batch.status != "PREVIEWED":
        raise AppError(409, "IMPORT_ALREADY_COMMITTED", "该导入批次已经确认")
    if any(row.action == "ERROR" for row in batch.rows):
        raise AppError(409, "IMPORT_HAS_ERRORS", "请先修正错误行后重新预览")
    if batch.summary.get("sync") != 1:
        raise AppError(409, "IMPORT_PREVIEW_EXPIRED", "导入规则已更新，请重新预览")
    imported_professions = _imported_professions(row.payload for row in batch.rows)
    existing_players = list(
        db.scalars(select(Player).options(selectinload(Player.characters)))
    )
    missing_players, missing_characters = _active_records_missing_from_import(
        existing_players, imported_professions
    )
    if (
        len(missing_characters) != batch.summary.get("deactivate", 0)
        or len(missing_players) != batch.summary.get("deactivate_players", 0)
        or _deactivation_fingerprint(missing_players, missing_characters)
        != batch.summary.get("deactivation_fingerprint")
    ):
        raise AppError(409, "IMPORT_DATA_CHANGED", "人员数据已变化，请重新预览")
    player_cache: dict[str, Player] = {}
    imported_player_ids: list[uuid.UUID] = []
    imported_player_id_set: set[uuid.UUID] = set()
    imported_character_ids: dict[uuid.UUID, list[uuid.UUID]] = {}
    imported_character_id_sets: dict[uuid.UUID, set[uuid.UUID]] = {}
    for row in batch.rows:
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
                    sort_order=0,
                )
                db.add(player)
                db.flush()
            player_cache[payload["player_key"]] = player
        player.is_active = True
        if player.id not in imported_player_id_set:
            imported_player_ids.append(player.id)
            imported_player_id_set.add(player.id)
        character = None
        if row.matched_character_id:
            character = db.get(Character, row.matched_character_id)
        if character is None:
            candidates = list(
                db.scalars(select(Character).where(Character.player_id == player.id))
            )
            matches = _profession_matches(candidates, payload)
            if len(matches) > 1:
                raise AppError(409, "IMPORT_DATA_CHANGED", "同玩家同职业角色不唯一，请重新预览")
            character = matches[0] if matches else None
        if character is None:
            character_id = uuid.uuid4()
            character = Character(
                id=character_id,
                player_id=player.id,
                name=str(payload["profession"]),
                name_key=str(payload["profession_key"]),
                sort_order=0,
            )
            db.add(character)
        player_character_ids = imported_character_ids.setdefault(player.id, [])
        player_character_id_set = imported_character_id_sets.setdefault(player.id, set())
        if character.id not in player_character_id_set:
            player_character_ids.append(character.id)
            player_character_id_set.add(character.id)
        if row.action != "IGNORE":
            _apply_payload(character, payload)

    for character in missing_characters:
        character.is_active = False
    for player in missing_players:
        player.is_active = False

    db.flush()
    all_players = list(
        db.scalars(
            select(Player).order_by(
                Player.sort_order,
                Player.display_name_key,
                Player.id,
            )
        )
    )
    player_by_id = {player.id: player for player in all_players}
    remaining_player_ids = [
        player.id for player in all_players if player.id not in imported_player_id_set
    ]
    for sort_order, player_id in enumerate(imported_player_ids + remaining_player_ids):
        player_by_id[player_id].sort_order = sort_order

    for player_id, ordered_ids in imported_character_ids.items():
        characters = list(
            db.scalars(
                select(Character)
                .where(Character.player_id == player_id)
                .order_by(Character.sort_order, Character.created_at, Character.id)
            )
        )
        imported_ids = imported_character_id_sets[player_id]
        remaining_ids = [
            character.id for character in characters if character.id not in imported_ids
        ]
        character_by_id = {character.id: character for character in characters}
        for sort_order, character_id in enumerate(ordered_ids + remaining_ids):
            character_by_id[character_id].sort_order = sort_order

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
    batch_id: uuid.UUID, db: DbSession, current_user: RosterImporter
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
    fields: dict[str, tuple[object, object]] = {
        "角色状态": (character.is_active, True),
        "职业": (character.profession, payload["profession"]),
        "类型": (character.role_type, payload["role_type"]),
        "伤害": (
            character.damage_score,
            _payload_decimal(payload["damage_score"]),
        ),
        "奶评分": (
            character.buffer_score,
            _payload_decimal(payload["buffer_score"]),
        ),
    }
    if _field_was_provided(payload, "is_treasure_damage"):
        fields["秘宝C"] = (character.is_treasure_damage, payload["is_treasure_damage"])
    if _field_was_provided(payload, "is_fixed_lead_team_buffer"):
        fields["固定红队奶"] = (
            character.is_fixed_lead_team_buffer,
            payload["is_fixed_lead_team_buffer"],
        )
    if _field_was_provided(payload, "is_group_hunt"):
        fields["群猎"] = (character.is_group_hunt, payload["is_group_hunt"])
    if _field_was_provided(payload, "note"):
        fields["备注"] = (character.note, payload["note"])
    if _field_was_provided(payload, "default_raid_participant"):
        fields["默认参团"] = (
            character.default_raid_participant,
            payload["default_raid_participant"],
        )
    return [name for name, (old, new) in fields.items() if old != new]


def _imported_professions(
    payloads: Iterable[dict[str, object]],
) -> dict[str, set[str]]:
    imported: dict[str, set[str]] = {}
    for payload in payloads:
        player_key = payload.get("player_key")
        profession_key = payload.get("profession_key")
        if isinstance(player_key, str) and isinstance(profession_key, str):
            imported.setdefault(player_key, set()).add(profession_key)
    return imported


def _active_records_missing_from_import(
    players: list[Player], imported_professions: dict[str, set[str]]
) -> tuple[list[Player], list[Character]]:
    missing_players: list[Player] = []
    missing_characters: list[Character] = []
    for player in players:
        professions = imported_professions.get(player.display_name_key)
        if professions is None:
            if player.is_active:
                missing_players.append(player)
            missing_characters.extend(
                character for character in player.characters if character.is_active
            )
            continue
        missing_characters.extend(
            character
            for character in player.characters
            if character.is_active and normalize_key(character.profession) not in professions
        )
    return missing_players, missing_characters


def _deactivation_fingerprint(
    players: list[Player], characters: list[Character]
) -> int:
    parts = [*(f"P:{player.id}" for player in players)]
    parts.extend(f"C:{character.id}" for character in characters)
    material = "\n".join(sorted(parts)).encode()
    return int(sha256(material).hexdigest()[:13], 16)


def _ordering_change_details(
    players: list[Player], rows: list[ImportRow]
) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    player_by_key = {player.display_name_key: player for player in players}
    imported_player_keys: list[str] = []
    imported_profession_keys: dict[str, list[str]] = {}
    for row in rows:
        player_key = str(row.payload["player_key"])
        profession_key = str(row.payload["profession_key"])
        if player_key not in imported_profession_keys:
            imported_player_keys.append(player_key)
            imported_profession_keys[player_key] = []
        imported_profession_keys[player_key].append(profession_key)

    imported_player_key_set = set(imported_player_keys)
    desired_player_keys = imported_player_keys + [
        player.display_name_key
        for player in players
        if player.display_name_key not in imported_player_key_set
    ]
    old_player_positions = {
        player.display_name_key: index for index, player in enumerate(players, start=1)
    }
    for new_position, player_key in enumerate(desired_player_keys, start=1):
        if player_key not in player_by_key:
            continue
        old_position = old_player_positions[player_key]
        if old_position != new_position:
            details.append(
                {
                    "action": "REORDER",
                    "player_name": player_by_key[player_key].display_name,
                    "profession": None,
                    "row_no": None,
                    "fields": [f"玩家顺序 {old_position} → {new_position}"],
                }
            )

    for player_key in imported_player_keys:
        if player_key not in player_by_key:
            continue
        player = player_by_key[player_key]
        current_characters = sorted(
            player.characters,
            key=lambda item: (item.sort_order, item.created_at, item.id),
        )
        character_by_key = {
            normalize_key(character.profession): character for character in current_characters
        }
        imported_keys = imported_profession_keys[player_key]
        imported_key_set = set(imported_keys)
        desired_character_keys = imported_keys + [
            normalize_key(character.profession)
            for character in current_characters
            if normalize_key(character.profession) not in imported_key_set
        ]
        old_character_positions = {
            normalize_key(character.profession): index
            for index, character in enumerate(current_characters, start=1)
        }
        for new_position, profession_key in enumerate(desired_character_keys, start=1):
            if profession_key not in character_by_key:
                continue
            old_position = old_character_positions[profession_key]
            if old_position != new_position:
                character = character_by_key[profession_key]
                details.append(
                    {
                        "action": "REORDER",
                        "player_name": player.display_name,
                        "profession": character.profession,
                        "row_no": None,
                        "fields": [f"角色顺序 {old_position} → {new_position}"],
                    }
                )
    return details


def _profession_matches(
    characters: list[Character], payload: dict[str, object]
) -> list[Character]:
    profession_key = str(payload["profession_key"])
    return [
        character
        for character in characters
        if normalize_key(character.profession) == profession_key
    ]


def _apply_payload(character: Character, payload: dict[str, object]) -> None:
    profession = str(payload["profession"])
    character.name = profession
    character.name_key = str(payload["profession_key"])
    character.profession = profession
    character.role_type = str(payload["role_type"])
    character.damage_score = payload["damage_score"]  # type: ignore[assignment]
    character.buffer_score = payload["buffer_score"]  # type: ignore[assignment]
    if _field_was_provided(payload, "is_treasure_damage"):
        character.is_treasure_damage = bool(payload["is_treasure_damage"])
    if _field_was_provided(payload, "is_fixed_lead_team_buffer"):
        character.is_fixed_lead_team_buffer = bool(payload["is_fixed_lead_team_buffer"])
    if _field_was_provided(payload, "is_group_hunt"):
        character.is_group_hunt = bool(payload["is_group_hunt"])
    if character.role_type == "DAMAGE":
        character.is_fixed_lead_team_buffer = False
    else:
        character.is_treasure_damage = False
        character.is_group_hunt = False
    if _field_was_provided(payload, "default_raid_participant"):
        character.default_raid_participant = bool(payload["default_raid_participant"])
    if _field_was_provided(payload, "note"):
        character.note = str(payload["note"]) if payload["note"] else None
    character.is_active = True


def _field_was_provided(payload: dict[str, object], field: str) -> bool:
    provided = payload.get("provided_fields")
    return isinstance(provided, list) and field in provided


def _payload_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii") or "download.xlsx"
    ascii_filename = (
        ascii_filename.replace("\\", "_").replace('"', "_").replace("\r", "").replace("\n", "")
    )
    encoded_filename = quote(filename, safe="")
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_filename}"; '
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )
