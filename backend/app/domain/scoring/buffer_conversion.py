from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEFAULT_BUFFER_CONVERSION_RULES = (
    {"profession": "奶爸", "multiplier": "0.997"},
    {"profession": "奶枪", "multiplier": "0.995"},
    {"profession": "奶妈", "multiplier": "1.000"},
    {"profession": "奶萝", "multiplier": "1.040"},
    {"profession": "缪斯", "multiplier": "1.002"},
)


def calculate_actual_buffer_score(
    standing_score: Decimal,
    profession: str,
    rules: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> Decimal:
    multiplier = next(
        (
            Decimal(str(rule["multiplier"]))
            for rule in rules
            if str(rule.get("profession", "")).strip().casefold()
            == profession.strip().casefold()
        ),
        Decimal("1.000"),
    )
    return (standing_score * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
