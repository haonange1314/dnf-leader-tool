from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.imports.characters import HEADERS, build_template, parse_character_workbook


def test_template_can_be_parsed() -> None:
    content = build_template()
    rows = parse_character_workbook(content, 100)
    workbook = load_workbook(BytesIO(content), read_only=True)
    sheet = workbook["角色数据"]

    assert tuple(cell.value for cell in sheet[1]) == HEADERS
    assert "角色名" not in HEADERS
    assert len(rows) == 1
    assert rows[0].payload["role_type"] == "DAMAGE"
    assert not rows[0].errors


def test_parser_reports_duplicate_and_invalid_row() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(HEADERS)
    sheet.append(("玩家A", "剑魂", "C", "120亿", "是", "是", ""))
    sheet.append(("玩家A", "剑魂", "未知", "x", "?", "是", ""))
    stream = BytesIO()
    workbook.save(stream)

    rows = parse_character_workbook(stream.getvalue(), 100)

    assert not rows[0].errors
    assert {error["code"] for error in rows[1].errors} >= {
        "DUPLICATE_ROW",
        "INVALID_ROLE",
        "INVALID_SCORE",
        "INVALID_BOOLEAN",
    }
