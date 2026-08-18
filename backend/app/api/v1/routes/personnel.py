import uuid
from typing import Any, cast

from fastapi import APIRouter, Query
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import AppError
from app.domain.personnel import normalize_key
from app.models.personnel import Character, Player
from app.schemas.personnel import (
    BatchUpdateResult,
    CharacterBatchUpdate,
    CharacterCreate,
    CharacterUpdate,
    CharacterView,
    PlayerCreate,
    PlayerList,
    PlayerUpdate,
    PlayerView,
)

router = APIRouter()


def _commit(db: DbSession, duplicate_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "PERSONNEL_DUPLICATE", duplicate_message) from exc


@router.get("/players", response_model=PlayerList)
def list_players(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = None,
    role_type: str | None = Query(default=None, alias="roleType", pattern="^(DAMAGE|BUFFER)$"),
    is_treasure: bool | None = Query(default=None, alias="isTreasure"),
    default_participant: bool | None = Query(default=None, alias="defaultParticipant"),
    is_active: bool | None = Query(default=None, alias="isActive"),
) -> PlayerList:
    del current_user
    stmt = select(Player).options(selectinload(Player.characters)).order_by(Player.display_name_key)
    filters = []
    if search:
        pattern = f"%{normalize_key(search)}%"
        stmt = stmt.join(Player.characters, isouter=True)
        filters.append(
            or_(Player.display_name_key.ilike(pattern), Character.name_key.ilike(pattern))
        )
    if is_active is not None:
        filters.append(Player.is_active == is_active)
    character_filters = []
    if role_type:
        character_filters.append(Character.role_type == role_type)
    if is_treasure is not None:
        character_filters.append(Character.is_treasure_damage == is_treasure)
    if default_participant is not None:
        character_filters.append(Character.default_raid_participant == default_participant)
    if character_filters:
        stmt = stmt.join(Player.characters)
        filters.extend(character_filters)
    if filters:
        stmt = stmt.where(*filters).distinct()
    players = list(db.scalars(stmt).unique())
    db.commit()
    return PlayerList(
        items=[PlayerView.model_validate(player) for player in players], total=len(players)
    )


@router.post("/players", response_model=PlayerView, status_code=201)
def create_player(payload: PlayerCreate, db: DbSession, current_user: CurrentUser) -> Player:
    del current_user
    player = Player(
        display_name=payload.display_name.strip(),
        display_name_key=normalize_key(payload.display_name),
        is_active=payload.is_active,
    )
    for item in payload.characters:
        player.characters.append(_new_character(item))
    db.add(player)
    _commit(db, "玩家称呼或同玩家角色名已存在")
    db.refresh(player)
    return player


@router.get("/players/{player_id}", response_model=PlayerView)
def get_player(player_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Player:
    del current_user
    player = db.scalar(
        select(Player).where(Player.id == player_id).options(selectinload(Player.characters))
    )
    if player is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    db.commit()
    return player


@router.patch("/players/{player_id}", response_model=PlayerView)
def update_player(
    player_id: uuid.UUID, payload: PlayerUpdate, db: DbSession, current_user: CurrentUser
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
    return player


@router.post("/players/{player_id}/characters", response_model=CharacterView, status_code=201)
def create_character(
    player_id: uuid.UUID, payload: CharacterCreate, db: DbSession, current_user: CurrentUser
) -> Character:
    del current_user
    if db.get(Player, player_id) is None:
        raise AppError(404, "PLAYER_NOT_FOUND", "玩家不存在")
    character = _new_character(payload, player_id)
    db.add(character)
    _commit(db, "该玩家下角色名已存在")
    db.refresh(character)
    return character


@router.patch("/characters/{character_id}", response_model=CharacterView)
def update_character(
    character_id: uuid.UUID, payload: CharacterUpdate, db: DbSession, current_user: CurrentUser
) -> Character:
    del current_user
    character = db.get(Character, character_id)
    if character is None:
        raise AppError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    _apply_character(character, payload)
    _commit(db, "该玩家下角色名已存在")
    db.refresh(character)
    return character


@router.post("/characters/{character_id}/deactivate", response_model=CharacterView)
def deactivate_character(
    character_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Character:
    del current_user
    character = db.get(Character, character_id)
    if character is None:
        raise AppError(404, "CHARACTER_NOT_FOUND", "角色不存在")
    character.is_active = False
    db.commit()
    db.refresh(character)
    return character


@router.post("/characters/batch-update", response_model=BatchUpdateResult)
def batch_update_characters(
    payload: CharacterBatchUpdate, db: DbSession, current_user: CurrentUser
) -> BatchUpdateResult:
    del current_user
    values: dict[str, bool] = {}
    if payload.is_active is not None:
        values["is_active"] = payload.is_active
    if payload.default_raid_participant is not None:
        values["default_raid_participant"] = payload.default_raid_participant
    result = cast(
        CursorResult[Any],
        db.execute(update(Character).where(Character.id.in_(payload.ids)).values(**values)),
    )
    if result.rowcount != len(payload.ids):
        db.rollback()
        raise AppError(404, "CHARACTER_NOT_FOUND", "部分角色不存在")
    db.commit()
    return BatchUpdateResult(updated=result.rowcount)


def _new_character(payload: CharacterCreate, player_id: uuid.UUID | None = None) -> Character:
    character = Character()
    if player_id is not None:
        character.player_id = player_id
    _apply_character(character, payload)
    return character


def _apply_character(character: Character, payload: CharacterCreate | CharacterUpdate) -> None:
    character.name = payload.name.strip()
    character.name_key = normalize_key(payload.name)
    character.profession = payload.profession.strip()
    character.role_type = payload.role_type.value
    character.damage_score = payload.damage_score
    character.buffer_score = payload.buffer_score
    character.is_treasure_damage = payload.is_treasure_damage
    character.default_raid_participant = payload.default_raid_participant
    character.note = payload.note.strip() if payload.note else None
    character.is_active = payload.is_active
