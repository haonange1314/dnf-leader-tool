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
    assert rows[0].payload["is_treasure_damage"] is True
    assert rows[0].payload["is_fixed_lead_team_buffer"] is False
    assert rows[0].payload["is_group_hunt"] is False
    assert not rows[0].errors


def test_parser_reports_duplicate_and_invalid_row() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(HEADERS)
    sheet.append((1, "玩家A", "剑魂", "C", "120亿", "是", "", "", "是"))
    sheet.append((2, "玩家A", "剑魂", "未知", "x", "?", "", "", "是"))
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


def test_parser_accepts_latest_roster_layout_and_two_decimal_buffer_score() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "米歇尔统计"
    sheet.append(HEADERS)
    sheet.append((1, "剑来", "奶萝", "奶", "4.75", "", "是", "", ""))
    sheet.append((2, "剑来", "光兵", "C", 1500, "", "", "是", "是"))
    workbook.create_sheet("军团-剑来小队").append(("这不是导入页",))
    stream = BytesIO()
    workbook.save(stream)

    rows = parse_character_workbook(stream.getvalue(), 100)

    assert len(rows) == 2
    assert rows[0].payload["buffer_score"] == "4.75"
    assert rows[0].payload["is_fixed_lead_team_buffer"] is True
    assert rows[0].payload["default_raid_participant"] is False
    assert rows[1].payload["damage_score"] == "1500"
    assert rows[1].payload["is_group_hunt"] is True
    assert rows[1].payload["default_raid_participant"] is True
    assert not rows[0].errors
    assert not rows[1].errors


def test_parser_keeps_legacy_seven_column_template_compatible() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(("玩家称呼", "职业", "类型", "伤害/增益量", "秘宝C", "默认参团", "备注"))
    sheet.append(("旧玩家", "剑魂", "C", 120, "否", "是", "旧模板"))
    stream = BytesIO()
    workbook.save(stream)

    rows = parse_character_workbook(stream.getvalue(), 100)

    assert len(rows) == 1
    assert rows[0].payload["note"] == "旧模板"
    assert rows[0].payload["is_fixed_lead_team_buffer"] is False
    assert rows[0].payload["is_group_hunt"] is False
    assert not rows[0].errors
