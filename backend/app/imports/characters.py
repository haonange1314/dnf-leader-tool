from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.workbook import Workbook as OpenpyxlWorkbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.personnel import normalize_key
from app.schemas.personnel import CharacterCreate, CharacterRole

HEADERS = (
    "序号",
    "玩家",
    "职业",
    "类型",
    "模拟伤害亿/站街奶量万",
)

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "sequence": ("序号",),
    "player_name": ("玩家",),
    "profession": ("职业",),
    "role_type": ("类型",),
    "score": ("模拟伤害亿/站街奶量万",),
}
REQUIRED_FIELDS = ("sequence", "player_name", "profession", "role_type", "score")


@dataclass(frozen=True)
class ParsedRow:
    row_no: int
    payload: dict[str, Any]
    errors: list[dict[str, str]]


@dataclass(frozen=True)
class CharacterExportRow:
    player_name: str
    profession: str
    role_type: str
    damage_score: Decimal | None
    buffer_score: Decimal | None


def build_template() -> bytes:
    workbook = _base_workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append((1, "示例玩家", "剑魂", "C", 120))
    sheet.auto_filter.ref = "A1:E2"
    return _save_workbook(workbook)


def build_roster_workbook(
    rows: list[CharacterExportRow],
) -> bytes:
    workbook = _base_workbook()
    sheet = workbook.active
    assert sheet is not None
    for sequence, row in enumerate(rows, start=1):
        score = row.damage_score if row.role_type == "DAMAGE" else row.buffer_score
        if (
            row.role_type == "DAMAGE"
            and score is not None
            and score != score.to_integral_value()
        ):
            raise ValueError(
                f"玩家“{row.player_name}”的职业“{row.profession}”仍有小数 C 伤害，请先修改为整数"
            )
        sheet.append(
            (
                sequence,
                row.player_name,
                row.profession,
                "C" if row.role_type == "DAMAGE" else "奶",
                int(score) if row.role_type == "DAMAGE" and score is not None else score,
            )
        )
    sheet.auto_filter.ref = f"A1:E{max(1, len(rows) + 1)}"
    return _save_workbook(workbook)


def _base_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "角色数据"
    sheet.append(HEADERS)
    sheet.freeze_panes = "A2"
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2937")
    widths = (8, 18, 16, 10, 28)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    role_validation = DataValidation(type="list", formula1='"C,奶"')
    sheet.add_data_validation(role_validation)
    role_validation.add("D2:D10001")
    notes = workbook.create_sheet("填写说明")
    notes.append(("字段", "说明"))
    notes.append(("类型", "填写 C 或 奶"))
    notes.append(("序号", "同一玩家内填写不重复的正整数；玩家按首次出现顺序、角色按表格行顺序导入"))
    notes.append(("模拟伤害亿/站街奶量万", "C 使用亿为单位且必须为整数，奶支持最多两位小数"))
    notes.append(
        (
            "玩家昵称修改",
            "导入以玩家和职业匹配；改名会被识别为删除旧玩家并新增玩家。",
        )
    )
    notes.append(("全量同步", "文件是人员真源：相同玩家和职业更新，不存在的新增，文件外记录删除。"))
    notes.freeze_panes = "A2"
    notes.column_dimensions["A"].width = 24
    notes.column_dimensions["B"].width = 88
    for cell in notes[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2937")
    for row in notes.iter_rows(min_row=2, max_col=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    return workbook


def _save_workbook(workbook: Workbook) -> bytes:
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def parse_character_workbook(
    content: bytes,
    max_rows: int,
) -> list[ParsedRow]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("无法读取 Excel 文件") from exc
    sheet, field_indexes = _find_import_sheet(workbook)
    rows: list[ParsedRow] = []
    seen: set[tuple[str, str]] = set()
    seen_sequences: set[tuple[str, int]] = set()
    for row_no, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        mapped_values = {
            field: values[index] if index < len(values) else None
            for field, index in field_indexes.items()
        }
        if not any(
            value is not None and str(value).strip()
            for field, value in mapped_values.items()
            if field != "sequence"
        ):
            continue
        if len(rows) >= max_rows:
            raise ValueError(f"导入行数不能超过 {max_rows}")
        payload, errors = _parse_row(mapped_values)
        key = (payload.get("player_key", ""), payload.get("profession_key", ""))
        if all(key):
            if key in seen:
                errors.append({"code": "DUPLICATE_ROW", "message": "文件内玩家与职业重复"})
            seen.add(key)
        sequence = payload.get("sequence")
        player_key = payload.get("player_key")
        if sequence is not None and isinstance(player_key, str) and player_key:
            sequence_key = (player_key, sequence)
            if sequence_key in seen_sequences:
                errors.append(
                    {"code": "DUPLICATE_SEQUENCE", "message": "同一玩家内序号重复"}
                )
            seen_sequences.add(sequence_key)
        rows.append(ParsedRow(row_no=row_no, payload=payload, errors=errors))
    if not rows:
        raise ValueError("导入文件中没有角色数据")
    return rows


def _find_import_sheet(workbook: OpenpyxlWorkbook) -> tuple[Worksheet, dict[str, int]]:
    for sheet in workbook.worksheets:
        headers = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
        while headers and not headers[-1]:
            headers.pop()
        indexes = {header: index for index, header in enumerate(headers) if header}
        field_indexes = {
            field: indexes[alias]
            for field, aliases in HEADER_ALIASES.items()
            for alias in aliases
            if alias in indexes
        }
        if tuple(headers) == HEADERS and not _has_extra_column_values(sheet):
            return sheet, field_indexes
    raise ValueError(
        "未找到表头完全匹配的角色数据工作表："
        "序号 | 玩家 | 职业 | 类型 | 模拟伤害亿/站街奶量万"
    )


def _has_extra_column_values(sheet: Worksheet) -> bool:
    if sheet.max_column <= len(HEADERS):
        return False
    return any(
        value is not None and str(value).strip()
        for row in sheet.iter_rows(
            min_row=2,
            min_col=len(HEADERS) + 1,
            max_col=sheet.max_column,
            values_only=True,
        )
        for value in row
    )


def _parse_row(values: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    player_name = _text(values.get("player_name"))
    profession = _text(values.get("profession"))
    role_raw = _text(values.get("role_type")).upper()
    errors: list[dict[str, str]] = []
    role_type = {"C": "DAMAGE", "DAMAGE": "DAMAGE", "奶": "BUFFER", "BUFFER": "BUFFER"}.get(
        role_raw
    )
    sequence = _positive_integer(values.get("sequence"), "序号", errors)
    for field, value in (
        ("玩家称呼", player_name),
        ("职业", profession),
    ):
        if not value:
            errors.append({"code": "REQUIRED", "message": f"{field}不能为空"})
    if role_type is None:
        errors.append({"code": "INVALID_ROLE", "message": "类型必须为 C 或 奶"})
    score = _decimal(values.get("score"), errors)
    if role_type == "DAMAGE" and score is not None and score != score.to_integral_value():
        errors.append({"code": "DAMAGE_SCORE_NOT_INTEGER", "message": "C 伤害必须为整数"})
    payload: dict[str, Any] = {
        "sequence": sequence,
        "player_name": player_name,
        "player_key": normalize_key(player_name),
        "profession": profession,
        "profession_key": normalize_key(profession),
        "role_type": role_type,
        "damage_score": str(score) if score is not None and role_type == "DAMAGE" else None,
        "buffer_score": str(score) if score is not None and role_type == "BUFFER" else None,
        "is_active": True,
        "provided_fields": ["sequence", "player_name", "profession", "role_type", "score"],
    }
    if not errors:
        assert role_type is not None
        try:
            CharacterCreate(
                profession=profession,
                role_type=CharacterRole(role_type),
                damage_score=payload["damage_score"],
                buffer_score=payload["buffer_score"],
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


def _positive_integer(value: Any, field: str, errors: list[dict[str, str]]) -> int | None:
    try:
        result = Decimal(_text(value))
    except InvalidOperation:
        errors.append({"code": "INVALID_SEQUENCE", "message": f"{field}必须为正整数"})
        return None
    if result <= 0 or result != result.to_integral_value():
        errors.append({"code": "INVALID_SEQUENCE", "message": f"{field}必须为正整数"})
        return None
    return int(result)


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
                payload.get("sequence"),
                payload.get("player_name"),
                payload.get("profession"),
                role,
                score,
                "；".join(str(error.get("message", "")) for error in errors),
            )
        )
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
