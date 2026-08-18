import pytest
from pydantic import ValidationError

from app.domain.personnel import normalize_key
from app.schemas.personnel import CharacterCreate


def test_normalize_key_uses_nfkc_casefold_and_trim() -> None:
    assert normalize_key("  Ａlice  ") == "alice"


def test_buffer_cannot_be_treasure_damage() -> None:
    with pytest.raises(ValidationError, match="只有 C"):
        CharacterCreate(
            name="奶妈",
            profession="炽天使",
            roleType="BUFFER",
            bufferScore="5.1",
            isTreasureDamage=True,
        )
