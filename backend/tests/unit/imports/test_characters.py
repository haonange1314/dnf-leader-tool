from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from app.imports.characters import (
    HEADERS,
    CharacterExportRow,
    build_roster_workbook,
    build_template,
    parse_character_workbook,
)


def _workbook(*rows: tuple[object, ...], headers: tuple[str, ...] = HEADERS) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_template_uses_exact_five_columns_and_can_be_parsed() -> None:
    content = build_template()
    sheet = load_workbook(BytesIO(content), read_only=True)["角色数据"]
    rows = parse_character_workbook(content, 100)

    assert tuple(cell.value for cell in sheet[1]) == HEADERS
    assert HEADERS == ("序号", "玩家", "职业", "类型", "模拟伤害亿/站街奶量万")
    assert rows[0].payload["sequence"] == 1
    assert rows[0].payload["role_type"] == "DAMAGE"
    assert not rows[0].errors


def test_parser_rejects_non_exact_headers() -> None:
    content = _workbook(
        (1, "玩家A", "剑魂", "C", 120),
        headers=("序号", "玩家昵称", "职业", "类型", "模拟伤害亿/站街奶量万"),
    )
    with pytest.raises(ValueError, match="表头完全匹配"):
        parse_character_workbook(content, 100)


def test_parser_accepts_trailing_formatted_empty_columns() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(HEADERS)
    sheet.append((1, "玩家A", "剑魂", "C", 120))
    sheet["N1"].fill = PatternFill("solid", fgColor="FFFFFF")
    stream = BytesIO()
    workbook.save(stream)

    rows = parse_character_workbook(stream.getvalue(), 100)

    assert len(rows) == 1
    assert not rows[0].errors


def test_parser_rejects_values_in_trailing_unnamed_columns() -> None:
    content = _workbook((1, "玩家A", "剑魂", "C", 120, "多余内容"))

    with pytest.raises(ValueError, match="表头完全匹配"):
        parse_character_workbook(content, 100)


def test_parser_reports_duplicate_key_sequence_and_invalid_values() -> None:
    rows = parse_character_workbook(
        _workbook(
            (1, "玩家A", "剑魂", "C", "120亿"),
            (1, "玩家A", "剑魂", "未知", "x"),
        ),
        100,
    )
    assert not rows[0].errors
    assert {error["code"] for error in rows[1].errors} >= {
        "DUPLICATE_ROW", "DUPLICATE_SEQUENCE", "INVALID_ROLE", "INVALID_SCORE"
    }


def test_parser_allows_sequence_reuse_by_different_players_and_preserves_rows() -> None:
    rows = parse_character_workbook(
        _workbook(
            (1, "玩家B", "剑魂", "C", 120),
            (2, "玩家B", "奶妈", "奶", "4.80"),
            (1, "玩家A", "红眼", "C", 110),
        ),
        100,
    )

    assert [row.payload["player_name"] for row in rows] == ["玩家B", "玩家B", "玩家A"]
    assert not any(row.errors for row in rows)


def test_parser_accepts_two_decimal_buffer_and_rejects_fractional_damage() -> None:
    rows = parse_character_workbook(
        _workbook(
            (1, "玩家A", "奶萝", "奶", "4.75"),
            (2, "玩家B", "剑魂", "C", "120.5"),
        ),
        100,
    )
    assert rows[0].payload["buffer_score"] == "4.75"
    assert not rows[0].errors
    assert rows[1].errors == [
        {"code": "DAMAGE_SCORE_NOT_INTEGER", "message": "C 伤害必须为整数"}
    ]


def test_physical_rows_control_import_order() -> None:
    rows = parse_character_workbook(
        _workbook(
            (2, "玩家B", "奶妈", "奶", "4.75"),
            (1, "玩家A", "剑魂", "C", "120"),
        ),
        100,
    )

    assert [row.payload["sequence"] for row in rows] == [2, 1]
    assert [row.payload["player_name"] for row in rows] == ["玩家B", "玩家A"]


def test_parser_rejects_empty_roster() -> None:
    with pytest.raises(ValueError, match="没有角色数据"):
        parse_character_workbook(_workbook(), 100)


def test_current_roster_export_round_trips_in_display_order() -> None:
    content = build_roster_workbook(
        [
            CharacterExportRow("玩家A", "剑魂", "DAMAGE", Decimal("120"), None),
            CharacterExportRow("玩家A", "奶妈", "BUFFER", None, Decimal("4.75")),
        ]
    )
    rows = parse_character_workbook(content, 100)
    assert [row.payload["profession"] for row in rows] == ["剑魂", "奶妈"]
    assert rows[0].payload["damage_score"] == "120"
    assert rows[1].payload["buffer_score"] == "4.75"
    assert not any(row.errors for row in rows)


def test_current_roster_export_rejects_fractional_damage() -> None:
    with pytest.raises(ValueError, match="仍有小数 C 伤害"):
        build_roster_workbook(
            [CharacterExportRow("玩家A", "剑魂", "DAMAGE", Decimal("120.5"), None)]
        )
