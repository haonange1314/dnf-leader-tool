import pytest
from pydantic import ValidationError

from app.domain.personnel import normalize_key
from app.schemas.personnel import CharacterCreate


def test_normalize_key_uses_nfkc_casefold_and_trim() -> None:
    assert normalize_key("  Ａlice  ") == "alice"


def test_buffer_score_keeps_two_decimal_places() -> None:
    character = CharacterCreate(
        profession="奶萝",
        roleType="BUFFER",
        bufferScore="4.75",
    )

    assert str(character.buffer_score) == "4.75"


def test_damage_score_must_be_an_integer() -> None:
    with pytest.raises(ValidationError, match="C 伤害必须为整数"):
        CharacterCreate(
            profession="剑魂",
            roleType="DAMAGE",
            damageScore="120.5",
        )


def test_new_character_defaults_to_active() -> None:
    character = CharacterCreate(
        profession="剑魂",
        roleType="DAMAGE",
        damageScore="120",
    )

    assert character.is_active is True
