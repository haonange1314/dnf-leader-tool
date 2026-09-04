import uuid
from decimal import Decimal

from app.api.v1.routes.imports import (
    _active_records_missing_from_import,
    _changes,
    _imported_professions,
    _ordering_change_details,
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
        is_treasure_damage=False,
        is_fixed_lead_team_buffer=False,
        is_group_hunt=False,
        default_raid_participant=True,
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


def test_full_sync_finds_players_and_characters_missing_from_workbook() -> None:
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
    missing_players, missing_characters = _active_records_missing_from_import(
        [imported_player, removed_player], imported
    )

    assert missing_players == [removed_player]
    assert missing_characters == [removed_character, removed_player_character]


def test_full_sync_does_not_repeat_deactivation_for_inactive_records() -> None:
    player = _player("玩家A", active=False)
    player.characters = [_character(player.id, "剑魂", active=False)]

    missing_players, missing_characters = _active_records_missing_from_import(
        [player], {}
    )

    assert missing_players == []
    assert missing_characters == []


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
