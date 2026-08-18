from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.domain.personnel import normalize_key
from app.schemas.personnel import CharacterCreate, CharacterRole

HEADERS = ("玩家称呼", "角色名", "职业", "类型", "伤害/增益量", "秘宝C", "默认参团", "备注")


@dataclass(frozen=True)
class ParsedRow:
    row_no: int
    payload: dict[str, Any]
    errors: list[dict[str, str]]


def build_template() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(HEADERS)
    sheet.append(("示例玩家", "示例C", "剑魂", "C", 120.5, "是", "是", "可删除示例行"))
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:H2"
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2937")
    widths = (18, 20, 16, 10, 18, 12, 12, 28)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    role_validation = DataValidation(type="list", formula1='"C,奶"')
    bool_validation = DataValidation(type="list", formula1='"是,否"')
    sheet.add_data_validation(role_validation)
    sheet.add_data_validation(bool_validation)
    role_validation.add("D2:D10001")
    bool_validation.add("F2:G10001")
    notes = workbook.create_sheet("填写说明")
    notes.append(("字段", "说明"))
    notes.append(("类型", "填写 C 或 奶"))
    notes.append(("伤害/增益量", "C 使用亿为单位，奶使用固定增益评分"))
    notes.append(("秘宝C/默认参团", "填写 是 或 否"))
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def parse_character_workbook(content: bytes, max_rows: int) -> list[ParsedRow]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("无法读取 Excel 文件") from exc
    if "角色数据" not in workbook.sheetnames:
        raise ValueError("缺少“角色数据”工作表")
    sheet = workbook["角色数据"]
    headers = tuple(str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1])
    if headers[: len(HEADERS)] != HEADERS:
        raise ValueError(f"列名必须为：{' | '.join(HEADERS)}")
    rows: list[ParsedRow] = []
    seen: set[tuple[str, str]] = set()
    for row_no, values in enumerate(
        sheet.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True), start=2
    ):
        if not any(value is not None and str(value).strip() for value in values):
            continue
        if len(rows) >= max_rows:
            raise ValueError(f"导入行数不能超过 {max_rows}")
        payload, errors = _parse_row(values)
        key = (payload.get("player_key", ""), payload.get("character_key", ""))
        if all(key):
            if key in seen:
                errors.append({"code": "DUPLICATE_ROW", "message": "文件内玩家与角色重复"})
            seen.add(key)
        rows.append(ParsedRow(row_no=row_no, payload=payload, errors=errors))
    return rows


def _parse_row(values: tuple[Any, ...]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    player_name = _text(values[0])
    character_name = _text(values[1])
    profession = _text(values[2])
    role_raw = _text(values[3]).upper()
    errors: list[dict[str, str]] = []
    role_type = {"C": "DAMAGE", "DAMAGE": "DAMAGE", "奶": "BUFFER", "BUFFER": "BUFFER"}.get(
        role_raw
    )
    for field, value in (
        ("玩家称呼", player_name),
        ("角色名", character_name),
        ("职业", profession),
    ):
        if not value:
            errors.append({"code": "REQUIRED", "message": f"{field}不能为空"})
    if role_type is None:
        errors.append({"code": "INVALID_ROLE", "message": "类型必须为 C 或 奶"})
    score = _decimal(values[4], errors)
    treasure = _boolean(values[5], "秘宝C", errors)
    default_participant = _boolean(values[6], "默认参团", errors)
    payload: dict[str, Any] = {
        "player_name": player_name,
        "player_key": normalize_key(player_name),
        "character_name": character_name,
        "character_key": normalize_key(character_name),
        "profession": profession,
        "role_type": role_type,
        "damage_score": str(score) if score is not None and role_type == "DAMAGE" else None,
        "buffer_score": str(score) if score is not None and role_type == "BUFFER" else None,
        "is_treasure_damage": treasure,
        "default_raid_participant": default_participant,
        "note": _text(values[7]) or None,
        "is_active": True,
    }
    if not errors:
        assert role_type is not None
        try:
            CharacterCreate(
                name=character_name,
                profession=profession,
                role_type=CharacterRole(role_type),
                damage_score=payload["damage_score"],
                buffer_score=payload["buffer_score"],
                is_treasure_damage=treasure,
                default_raid_participant=default_participant,
                note=payload["note"],
            )
        except ValueError as exc:
            errors.append({"code": "INVALID_CHARACTER", "message": str(exc)})
    return payload, errors


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any, errors: list[dict[str, str]]) -> Decimal | None:
    raw = _text(value).removesuffix("亿")
    try:
        result = Decimal(raw)
    except InvalidOperation:
        errors.append({"code": "INVALID_SCORE", "message": "伤害/增益量必须是数字"})
        return None
    if result < 0:
        errors.append({"code": "INVALID_SCORE", "message": "伤害/增益量不能小于 0"})
    return result


def _boolean(value: Any, field: str, errors: list[dict[str, str]]) -> bool:
    normalized = _text(value).casefold()
    if normalized in {"是", "y", "yes", "1", "true"}:
        return True
    if normalized in {"否", "n", "no", "0", "false"}:
        return False
    errors.append({"code": "INVALID_BOOLEAN", "message": f"{field}必须为是或否"})
    return False


def build_error_workbook(rows: list[tuple[int, dict[str, Any], list[dict[str, Any]]]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "错误明细"
    sheet.append(("原行号", *HEADERS, "错误"))
    for row_no, payload, errors in rows:
        role = "C" if payload.get("role_type") == "DAMAGE" else "奶"
        score = payload.get("damage_score") or payload.get("buffer_score")
        sheet.append(
            (
                row_no,
                payload.get("player_name"),
                payload.get("character_name"),
                payload.get("profession"),
                role,
                score,
                "是" if payload.get("is_treasure_damage") else "否",
                "是" if payload.get("default_raid_participant") else "否",
                payload.get("note"),
                "；".join(str(error.get("message", "")) for error in errors),
            )
        )
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
