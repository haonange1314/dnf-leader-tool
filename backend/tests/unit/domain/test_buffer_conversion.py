from decimal import Decimal

from app.domain.scoring.buffer_conversion import calculate_actual_buffer_score


def test_actual_buffer_score_uses_profession_multiplier_and_rounds_half_up() -> None:
    rules = [{"profession": "奶萝", "multiplier": "1.040"}]

    assert calculate_actual_buffer_score(Decimal("4.75"), "奶萝", rules) == Decimal(
        "4.94"
    )


def test_unconfigured_profession_keeps_standing_score() -> None:
    assert calculate_actual_buffer_score(Decimal("4.75"), "未知奶", []) == Decimal(
        "4.75"
    )


def test_profession_matching_ignores_surrounding_whitespace() -> None:
    rules = [{"profession": " 奶爸 ", "multiplier": "0.997"}]

    assert calculate_actual_buffer_score(Decimal("4.75"), "奶爸", rules) == Decimal(
        "4.74"
    )
