import uuid
from typing import Any, cast

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, RosterReader, RosterWriter
from app.core.errors import AppError
from app.domain.personnel import normalize_key
from app.domain.scoring.buffer_conversion import calculate_actual_buffer_score
from app.models.buffer_conversion import BufferConversionVersion
from app.models.personnel import Character, Player
from app.schemas.personnel import (
    BatchUpdateResult,
    CharacterBatchUpdate,
    CharacterCreate,
    CharacterUpdate,
    CharacterView,
    PersonnelReorder,
    PlayerCreate,
    PlayerList,
    PlayerUpdate,
    PlayerView,
)

router = APIRouter()


def _annotate_actual_scores(db: DbSession, characters: list[Character]) -> None:
    version = db.scalar(
        select(BufferConversionVersion)
        .where(BufferConversionVersion.is_active.is_(True))
        .order_by(BufferConversionVersion.version.desc())
        .limit(1)
    )
    rules = version.rules if version is not None else []
    for character in characters:
        actual = (
            calculate_actual_buffer_score(character.buffer_score, character.profession, rules)
            if character.role_type == "BUFFER" and character.buffer_score is not None
            else None
        )
        character.actual_buffer_score = actual


def _commit(db: DbSession, duplicate_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "PERSONNEL_DUPLICATE", duplicate_message) from exc


@router.get("/players", response_model=PlayerList)
def list_players(
    db: DbSession,
    current_user: RosterReader,
    search: str | None = None,
    role_type: str | None = Query(default=None, alias="roleType", pattern="^(DAMAGE|BUFFER)$"),
    is_active: bool | None = Query(default=None, alias="isActive"),
) -> PlayerList:
    del current_user
    stmt = (
        select(Player)
        .options(selectinload(Player.characters))
        .order_by(Player.sort_order, Player.display_name_key, Player.id)
    )
    filters = []
    if search:
        pattern = f"%{normalize_key(search)}%"
        stmt = stmt.join(Player.characters, isouter=True)
        filters.append(
            or_(Player.display_name_key.ilike(pattern), Character.profession.ilike(pattern))
        )
    if is_active is not None:
        filters.append(Player.is_active == is_active)
    character_filters = []
    if role_type:
        character_filters.append(Character.role_type == role_type)
    if character_filters:
        stmt = stmt.join(Player.characters)
        filters.extend(character_filters)
    if filters:
        stmt = stmt.where(*filters).distinct()
    players = list(db.scalars(stmt).unique())
    _annotate_actual_scores(
        db, [character for player in players for character in player.characters]
    )
    db.commit()
    return PlayerList(
        items=[PlayerView.model_validate(player) for player in players], total=len(players)
    )


@router.post("/players", response_model=PlayerView, status_code=201)
def create_player(payload: PlayerCreate, db: DbSession, current_user: RosterWriter) -> Player:
    del current_user
    player = Player(
        display_name=payload.display_name.strip(),
        display_name_key=normalize_key(payload.display_name),
        is_active=payload.is_active,
        sort_order=_next_player_sort_order(db),
    )
    for sort_order, item in enumerate(payload.characters):
        player.characters.append(_new_character(item, sort_order=sort_order))
    db.add(player)
    _commit(db, "玩家称呼或同玩家相同职业已存在")
    db.refresh(player)
    _annotate_actual_scores(db, list(player.characters))
    return player


@router.put("/players/reorder", response_model=BatchUpdateResult)
def reorder_players(
    payload: PersonnelReorder, db: DbSession, current_user: RosterWriter
) -> BatchUpdateResult:
    del current_user
    players = list(db.scalars(select(Player)))
    players_by_id = {player.id: player for player in players}
    if set(payload.ordered_ids) != set(players_by_id):
        raise AppError(409, "PERSONNEL_ORDER_CHANGED", "玩家列表已变化，请刷新后重试")
    for sort_order, player_id in enumerate(payload.ordered_ids):
        players_by_id[player_id].sort_order = sort_order
    db.commit()
    return BatchUpdateResult(updated=len(players))


@router.get("/players/{player_id}", response_model=PlayerView)
def get_player(player_id: uuid.UUID, db: DbSession, current_user: RosterReader) -> Player:
    del current_user
    player = db.scalar(
        select(Player).where(Player.id == player_id).options(selectinload(Player.characters))
    )
    if player is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    _annotate_actual_scores(db, list(player.characters))
    db.commit()
    return player


@router.patch("/players/{player_id}", response_model=PlayerView)
def update_player(
    player_id: uuid.UUID, payload: PlayerUpdate, db: DbSession, current_user: RosterWriter
) -> Player:
    del current_user
    player = db.get(Player, player_id)
    if player is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    player.display_name = payload.display_name.strip()
    player.display_name_key = normalize_key(payload.display_name)
    player.is_active = payload.is_active
    _commit(db, "玩家称呼已存在")
    db.refresh(player)
    _annotate_actual_scores(db, list(player.characters))
    return player


@router.delete("/players/{player_id}", status_code=204)
def delete_player(
    player_id: uuid.UUID, db: DbSession, current_user: RosterWriter
) -> None:
    del current_user
    player = db.scalar(
        select(Player)
        .where(Player.id == player_id)
        .options(selectinload(Player.characters))
        .with_for_update()
    )
    if player is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    db.delete(player)
    db.commit()


@router.post("/players/{player_id}/characters", response_model=CharacterView, status_code=201)
def create_character(
    player_id: uuid.UUID, payload: CharacterCreate, db: DbSession, current_user: RosterWriter
) -> Character:
    del current_user
    if db.get(Player, player_id) is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    character = _new_character(
        payload, player_id, sort_order=_next_character_sort_order(db, player_id)
    )
    db.add(character)
    _commit(db, "同一玩家不能存在相同职业")
    db.refresh(character)
    _annotate_actual_scores(db, [character])
    return character


@router.put("/players/{player_id}/characters/reorder", response_model=BatchUpdateResult)
def reorder_characters(
    player_id: uuid.UUID,
    payload: PersonnelReorder,
    db: DbSession,
    current_user: RosterWriter,
) -> BatchUpdateResult:
    del current_user
    if db.get(Player, player_id) is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    characters = list(db.scalars(select(Character).where(Character.player_id == player_id)))
    characters_by_id = {character.id: character for character in characters}
    if set(payload.ordered_ids) != set(characters_by_id):
        raise AppError(409, "PERSONNEL_ORDER_CHANGED", "角色列表已变化，请刷新后重试")
    for sort_order, character_id in enumerate(payload.ordered_ids):
        characters_by_id[character_id].sort_order = sort_order
    db.commit()
    return BatchUpdateResult(updated=len(characters))


@router.patch("/characters/{character_id}", response_model=CharacterView)
def update_character(
    character_id: uuid.UUID, payload: CharacterUpdate, db: DbSession, current_user: RosterWriter
) -> Character:
    del current_user
    character = db.get(Character, character_id)
    if character is None:
        raise AppError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    _apply_character(character, payload)
    _commit(db, "同一玩家不能存在相同职业")
    db.refresh(character)
    _annotate_actual_scores(db, [character])
    return character


@router.delete("/characters/{character_id}", status_code=204)
def delete_character(
    character_id: uuid.UUID, db: DbSession, current_user: RosterWriter
) -> None:
    del current_user
    character = db.get(Character, character_id, with_for_update=True)
    if character is None:
        raise AppError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    db.delete(character)
    db.commit()


@router.post("/characters/{character_id}/deactivate", response_model=CharacterView)
def deactivate_character(
    character_id: uuid.UUID, db: DbSession, current_user: RosterWriter
) -> Character:
    del current_user
    character = db.get(Character, character_id)
    if character is None:
        raise AppError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    character.is_active = False
    db.commit()
    db.refresh(character)
    _annotate_actual_scores(db, [character])
    return character


@router.post("/characters/batch-update", response_model=BatchUpdateResult)
def batch_update_characters(
    payload: CharacterBatchUpdate, db: DbSession, current_user: RosterWriter
) -> BatchUpdateResult:
    del current_user
    values: dict[str, bool] = {}
    if payload.is_active is not None:
        values["is_active"] = payload.is_active
    result = cast(
        CursorResult[Any],
        db.execute(update(Character).where(Character.id.in_(payload.ids)).values(**values)),
    )
    if result.rowcount != len(payload.ids):
        db.rollback()
        raise AppError(404, "CHARACTER_NOT_FOUND", "部分角色不存在")
    db.commit()
    return BatchUpdateResult(updated=result.rowcount)


def _next_player_sort_order(db: DbSession) -> int:
    current = db.scalar(select(func.max(Player.sort_order)))
    return int(current) + 1 if current is not None else 0


def _next_character_sort_order(db: DbSession, player_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(Character.sort_order)).where(Character.player_id == player_id)
    )
    return int(current) + 1 if current is not None else 0


def _new_character(
    payload: CharacterCreate,
    player_id: uuid.UUID | None = None,
    *,
    sort_order: int = 0,
) -> Character:
    character_id = uuid.uuid4()
    character = Character(
        id=character_id,
        name=payload.profession.strip(),
        name_key=normalize_key(payload.profession),
        sort_order=sort_order,
    )
    if player_id is not None:
        character.player_id = player_id
    _apply_character(character, payload)
    return character


def _apply_character(character: Character, payload: CharacterCreate | CharacterUpdate) -> None:
    profession = payload.profession.strip()
    character.name = profession
    character.name_key = normalize_key(profession)
    character.profession = profession
    character.role_type = payload.role_type.value
    character.damage_score = payload.damage_score
    character.buffer_score = payload.buffer_score
    character.is_active = payload.is_active
