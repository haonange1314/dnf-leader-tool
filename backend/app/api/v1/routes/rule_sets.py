from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession, ScheduleEditor
from app.application.schedule_rules import (
    build_rule_context,
    build_rule_provider,
    consume_rule_parse_quota,
    serialize_resolution_issues,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.domain.schedule.rules import resolve_rule_output, rule_context_hash, source_text_hash
from app.integrations.deepseek_rules import RuleProviderError
from app.models.schedule import Schedule, ScheduleRuleSet, Team, Wave
from app.schemas.schedule_rules import (
    ScheduleRuleSetClearRequest,
    ScheduleRuleSetConfirmRequest,
    ScheduleRuleSetList,
    ScheduleRuleSetMutationResponse,
    ScheduleRuleSetParseRequest,
    ScheduleRuleSetView,
)

router = APIRouter()


def _load_schedule(db: DbSession, schedule_id: uuid.UUID, *, for_update: bool = False) -> Schedule:
    statement = (
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(
            selectinload(Schedule.participants),
            selectinload(Schedule.waves).selectinload(Wave.teams).selectinload(Team.slots),
            selectinload(Schedule.active_rule_set),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    schedule = db.scalar(statement)
    if schedule is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    return schedule


def _require_revision(schedule: Schedule, base_revision: int) -> None:
    if schedule.revision != base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": base_revision, "current": schedule.revision},
        )


@router.post(
    "/schedules/{schedule_id}/rule-sets/parse",
    response_model=ScheduleRuleSetView,
)
def parse_rule_set(
    schedule_id: uuid.UUID,
    payload: ScheduleRuleSetParseRequest,
    db: DbSession,
    current_user: ScheduleEditor,
) -> ScheduleRuleSetView:
    settings = get_settings()
    if not settings.natural_language_rules_enabled:
        raise AppError(503, "NATURAL_LANGUAGE_RULES_DISABLED", "自然语言排表规则尚未启用")
    if len(payload.source_text) > settings.natural_language_rule_max_chars:
        raise AppError(
            422,
            "RULE_SET_SOURCE_TOO_LONG",
            f"本次排表要求不能超过 {settings.natural_language_rule_max_chars} 个字符",
        )
    schedule = _load_schedule(db, schedule_id)
    _require_revision(schedule, payload.base_revision)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能解析规则")
    context = build_rule_context(schedule)
    context_digest = rule_context_hash(context)
    source_digest = source_text_hash(payload.source_text)
    consume_rule_parse_quota(db, current_user.id, settings)
    db.commit()

    try:
        provider = build_rule_provider(settings)
        try:
            provider_result = provider.interpret(payload.source_text, context)
        finally:
            provider.close()
    except ValueError as exc:
        raise AppError(503, "NATURAL_LANGUAGE_RULES_DISABLED", str(exc)) from exc
    except RuleProviderError as exc:
        raise AppError(503, exc.code, str(exc)) from exc

    resolution = resolve_rule_output(provider_result.output, context)
    record = ScheduleRuleSet(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        input_revision=schedule.revision,
        source_text=payload.source_text,
        source_hash=source_digest,
        context_hash=context_digest,
        status="PARSED",
        model_provider=provider_result.provider,
        model_name=provider_result.model,
        provider_response_id=provider_result.response_id,
        prompt_version=settings.rule_prompt_version,
        schema_version=provider_result.output.schema_version,
        parsed_rules=list(resolution.rules),
        resolved_references=resolution.resolved_references,
        issues=serialize_resolution_issues(resolution.issues),
        created_by=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ScheduleRuleSetView.model_validate(record)


@router.get(
    "/schedules/{schedule_id}/rule-sets",
    response_model=ScheduleRuleSetList,
)
def list_rule_sets(
    schedule_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ScheduleRuleSetList:
    del current_user
    settings = get_settings()
    schedule = _load_schedule(db, schedule_id)
    records = list(
        db.scalars(
            select(ScheduleRuleSet)
            .where(ScheduleRuleSet.schedule_id == schedule_id)
            .order_by(ScheduleRuleSet.created_at.desc())
        )
    )
    return ScheduleRuleSetList(
        items=[ScheduleRuleSetView.model_validate(record) for record in records],
        total=len(records),
        active_rule_set_id=schedule.active_rule_set_id,
        revision=schedule.revision,
        max_source_chars=settings.natural_language_rule_max_chars,
        parsing_enabled=settings.natural_language_rules_enabled,
    )


@router.post(
    "/schedules/{schedule_id}/rule-sets/{rule_set_id}/confirm",
    response_model=ScheduleRuleSetMutationResponse,
)
def confirm_rule_set(
    schedule_id: uuid.UUID,
    rule_set_id: uuid.UUID,
    payload: ScheduleRuleSetConfirmRequest,
    db: DbSession,
    current_user: ScheduleEditor,
) -> ScheduleRuleSetMutationResponse:
    schedule = _load_schedule(db, schedule_id, for_update=True)
    _require_revision(schedule, payload.base_revision)
    record = db.get(ScheduleRuleSet, rule_set_id)
    if record is None or record.schedule_id != schedule_id:
        raise AppError(404, "RULE_SET_NOT_FOUND", "规则解析记录不存在")
    if record.status != "PARSED":
        raise AppError(409, "RULE_SET_NOT_CONFIRMABLE", "当前规则解析记录不能确认")
    if record.source_hash != payload.source_hash or record.context_hash != payload.context_hash:
        raise AppError(409, "RULE_SET_PREVIEW_STALE", "规则预览已变化，请重新解析")
    current_context_hash = rule_context_hash(build_rule_context(schedule))
    if current_context_hash != record.context_hash:
        record.status = "STALE"
        db.commit()
        raise AppError(409, "RULE_SET_CONTEXT_STALE", "排表上下文已变化，请重新解析")
    if record.issues:
        raise AppError(
            422,
            "RULE_SET_HAS_BLOCKING_ISSUES",
            "规则存在歧义、未知引用或不支持内容，不能确认",
            details={"issues": record.issues},
        )
    if schedule.active_rule_set is not None:
        schedule.active_rule_set.status = "SUPERSEDED"
        db.flush()
    record.status = "CONFIRMED"
    record.confirmed_by = current_user.id
    record.confirmed_at = utc_now()
    schedule.active_rule_set_id = record.id
    schedule.revision += 1
    schedule.updated_by = current_user.id
    schedule.updated_at = utc_now()
    schedule.status = "DRAFT"
    db.commit()
    db.refresh(record)
    return ScheduleRuleSetMutationResponse(
        revision=schedule.revision,
        active_rule_set_id=record.id,
        rule_set=ScheduleRuleSetView.model_validate(record),
    )


@router.post(
    "/schedules/{schedule_id}/rule-sets/clear",
    response_model=ScheduleRuleSetMutationResponse,
)
def clear_rule_set(
    schedule_id: uuid.UUID,
    payload: ScheduleRuleSetClearRequest,
    db: DbSession,
    current_user: ScheduleEditor,
) -> ScheduleRuleSetMutationResponse:
    schedule = _load_schedule(db, schedule_id, for_update=True)
    _require_revision(schedule, payload.base_revision)
    if schedule.active_rule_set is None:
        return ScheduleRuleSetMutationResponse(
            revision=schedule.revision, active_rule_set_id=None, rule_set=None
        )
    schedule.active_rule_set.status = "SUPERSEDED"
    schedule.active_rule_set_id = None
    schedule.revision += 1
    schedule.updated_by = current_user.id
    schedule.updated_at = utc_now()
    schedule.status = "DRAFT"
    db.commit()
    return ScheduleRuleSetMutationResponse(
        revision=schedule.revision, active_rule_set_id=None, rule_set=None
    )
