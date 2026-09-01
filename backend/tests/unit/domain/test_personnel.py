import pytest
from pydantic import ValidationError

from app.domain.personnel import normalize_key
from app.schemas.personnel import CharacterCreate


def test_normalize_key_uses_nfkc_casefold_and_trim() -> None:
    assert normalize_key("  Ａlice  ") == "alice"


def test_buffer_cannot_be_treasure_damage() -> None:
    with pytest.raises(ValidationError, match="只有 C"):
        CharacterCreate(
            profession="炽天使",
            roleType="BUFFER",
            bufferScore="5.1",
            isTreasureDamage=True,
        )


def test_character_trait_role_constraints() -> None:
    with pytest.raises(ValidationError, match="固定红队奶"):
        CharacterCreate(
            profession="剑魂",
            roleType="DAMAGE",
            damageScore="5000",
            isFixedLeadTeamBuffer=True,
        )
    with pytest.raises(ValidationError, match="群猎"):
        CharacterCreate(
            profession="奶妈",
            roleType="BUFFER",
            bufferScore="4.75",
            isGroupHunt=True,
        )


def test_buffer_score_keeps_two_decimal_places() -> None:
    character = CharacterCreate(
        profession="奶萝",
        roleType="BUFFER",
        bufferScore="4.75",
    )

    assert str(character.buffer_score) == "4.75"
