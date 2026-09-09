import uuid
from decimal import Decimal

from app.api.v1.routes.imports import (
    _changes,
    _imported_professions,
    _ordering_change_details,
    _roster_sync_plan,
)
from app.models.imports import ImportRow
from app.models.personnel import Character, Player


def _character(
    player_id: uuid.UUID, profession: str, *, active: bool = True
) -> Character:
    return Character(
        id=uuid.uuid4(),
        player_id=player_id,
        name=profession,
        name_key=profession.casefold(),
        profession=profession,
        role_type="DAMAGE",
        damage_score=Decimal("100"),
        buffer_score=None,
        note=None,
        is_active=active,
        sort_order=0,
    )


def _player(name: str, *, active: bool = True) -> Player:
    player_id = uuid.uuid4()
    return Player(
        id=player_id,
        display_name=name,
        display_name_key=name.casefold(),
        is_active=active,
        sort_order=0,
        characters=[],
    )


def test_full_sync_deletes_unreferenced_players_and_characters() -> None:
    imported_player = _player("玩家A")
    kept = _character(imported_player.id, "剑魂")
    removed_character = _character(imported_player.id, "红眼")
    already_inactive = _character(imported_player.id, "鬼泣", active=False)
    imported_player.characters = [kept, removed_character, already_inactive]

    removed_player = _player("玩家B")
    removed_player_character = _character(removed_player.id, "奶妈")
    removed_player.characters = [removed_player_character]

    imported = _imported_professions(
        [{"player_key": "玩家a", "profession_key": "剑魂"}]
    )
    plan = _roster_sync_plan(
        [imported_player, removed_player],
        imported,
    )

    assert plan.delete_players == [removed_player]
    assert plan.delete_characters == [
        removed_character,
        already_inactive,
    ]


def test_full_sync_hard_deletes_players_and_safe_siblings() -> None:
    player = _player("玩家A")
    referenced = _character(player.id, "剑魂")
    unreferenced = _character(player.id, "红眼")
    player.characters = [referenced, unreferenced]

    plan = _roster_sync_plan(
        [player],
        {},
    )

    assert plan.delete_players == [player]
    assert plan.delete_characters == []


def test_preview_compares_decimal_scores_by_value() -> None:
    player = _player("玩家A")
    character = _character(player.id, "剑魂")

    changes = _changes(
        character,
        {
            "profession": "剑魂",
            "role_type": "DAMAGE",
            "damage_score": "100.00",
            "buffer_score": None,
            "provided_fields": [],
        },
    )

    assert changes == []


def test_full_sync_preview_reports_player_and_character_reordering() -> None:
    player_a = _player("玩家A")
    player_a.sort_order = 0
    character_a = _character(player_a.id, "剑魂")
    character_b = _character(player_a.id, "红眼")
    character_a.sort_order = 0
    character_b.sort_order = 1
    player_a.characters = [character_a, character_b]
    player_b = _player("玩家B")
    player_b.sort_order = 1
    player_b.characters = [_character(player_b.id, "奶妈")]
    rows = [
        ImportRow(
            row_no=2,
            action="IGNORE",
            payload={"player_key": "玩家b", "profession_key": "奶妈"},
            errors=[],
        ),
        ImportRow(
            row_no=3,
            action="IGNORE",
            payload={"player_key": "玩家a", "profession_key": "红眼"},
            errors=[],
        ),
        ImportRow(
            row_no=4,
            action="IGNORE",
            payload={"player_key": "玩家a", "profession_key": "剑魂"},
            errors=[],
        ),
    ]

    details = _ordering_change_details([player_a, player_b], rows)

    assert {tuple(item["fields"]) for item in details} == {
        ("玩家顺序 1 → 2",),
        ("玩家顺序 2 → 1",),
        ("角色顺序 1 → 2",),
        ("角色顺序 2 → 1",),
    }
