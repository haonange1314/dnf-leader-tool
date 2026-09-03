import time
import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, ScheduleGeneratorEditor, ScheduleReader
from app.application.schedule_generation import (
    SOLVER_VERSION,
    apply_solver_result,
    build_solver_input,
    clear_regeneratable_assignments,
    objective_summary_payload,
    solver_diagnostics_payload,
    solver_input_hash,
)
from app.application.schedule_locks import require_edit_lock
from app.application.schedule_rules import (
    active_rule_set_context_is_current,
    compile_rule_set,
    invalidate_active_rule_set,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.domain.schedule.rules import (
    RULE_COMPILER_VERSION,
    blocked_generation_rule_evaluation,
    evaluate_compiled_rules,
    evaluate_locked_rule_blockers,
)
from app.models.dungeon import DungeonVersion, FormulaVersion
from app.models.schedule import GenerationRun, Schedule, Team, Wave
from app.schemas.schedule import (
    GenerationRequest,
    GenerationResponse,
    GenerationRunList,
    GenerationRunView,
    ScheduleDetail,
)
from app.solver import SolverStatus, solve

router = APIRouter()


def _load_schedule(db: DbSession, schedule_id: uuid.UUID, *, for_update: bool = False) -> Schedule:
    statement = (
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(
            selectinload(Schedule.participants),
            selectinload(Schedule.preferences),
            selectinload(Schedule.waves).selectinload(Wave.special_assignments),
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


def _load_definition(db: DbSession, schedule: Schedule) -> tuple[DungeonVersion, FormulaVersion]:
    version = db.scalar(
        select(DungeonVersion)
        .where(DungeonVersion.id == schedule.dungeon_version_id)
        .options(
            selectinload(DungeonVersion.teams),
            selectinload(DungeonVersion.dungeon),
        )
    )
    formula = db.get(FormulaVersion, schedule.formula_version_id)
    if version is None or formula is None:
        raise AppError(409, "SCHEDULE_DEFINITION_MISSING", "排表引用的副本或公式版本不存在")
    return version, formula


@router.post("/schedules/{schedule_id}/generate", response_model=GenerationResponse)
def generate_schedule(
    schedule_id: uuid.UUID,
    payload: GenerationRequest,
    request: Request,
    db: DbSession,
    current_user: ScheduleGeneratorEditor,
) -> GenerationResponse:
    schedule = _load_schedule(db, schedule_id)
    if schedule.status == "ARCHIVED":
        raise AppError(409, "SCHEDULE_ARCHIVED", "已归档排表不能自动生成")
    if schedule.revision != payload.base_revision:
        raise AppError(
            409,
            "SCHEDULE_REVISION_CONFLICT",
            "排表已被其他操作修改，请刷新后重试",
            details={"expected": payload.base_revision, "current": schedule.revision},
        )
    if schedule.active_rule_set_id != payload.expected_rule_set_id:
        raise AppError(
            409,
            "RULE_SET_CONTEXT_STALE",
            "当前生效规则已变化，请刷新后重新生成",
            details={
                "expected": str(payload.expected_rule_set_id)
                if payload.expected_rule_set_id
                else None,
                "current": str(schedule.active_rule_set_id)
                if schedule.active_rule_set_id
                else None,
            },
        )
    if not active_rule_set_context_is_current(schedule):
        invalidate_active_rule_set(schedule)
        schedule.revision += 1
        schedule.updated_by = current_user.id
        schedule.updated_at = utc_now()
        schedule.status = "DRAFT"
        schedule.validation_summary = None
        db.commit()
        raise AppError(
            409,
            "RULE_SET_CONTEXT_STALE",
            "玩家波次或排表结构已变化，请重新解析本次排表要求",
            details={"currentRevision": schedule.revision},
        )
    settings = get_settings()
    random_seed = (
        payload.random_seed if payload.random_seed is not None else settings.solver_random_seed
    )
    time_limit_seconds = (
        payload.time_limit_seconds
        if payload.time_limit_seconds is not None
        else settings.solver_time_limit_seconds
    )
    version, formula = _load_definition(db, schedule)
    schedule_rules = compile_rule_set(schedule.active_rule_set)
    try:
        solver_input = build_solver_input(
            schedule,
            version,
            formula,
            preserve_locks=payload.preserve_locks,
            random_seed=random_seed,
            time_limit_seconds=time_limit_seconds,
            schedule_rules=schedule_rules,
        )
    except ValueError as exc:
        raise AppError(422, "SOLVER_INPUT_INVALID", str(exc)) from exc
    run = GenerationRun(
        id=uuid.uuid4(),
        schedule_id=schedule.id,
        input_revision=schedule.revision,
        status="RUNNING",
        input_hash=solver_input_hash(solver_input),
        solver_version=SOLVER_VERSION,
        formula_version_id=schedule.formula_version_id,
        schedule_rule_set_id=schedule.active_rule_set_id,
        rule_compiler_version=RULE_COMPILER_VERSION if schedule_rules else None,
        effective_rules=(
            schedule.active_rule_set.parsed_rules if schedule.active_rule_set else None
        ),
        random_seed=random_seed,
        time_limit_seconds=time_limit_seconds,
        created_by=current_user.id,
    )
    db.add(run)
    db.commit()

    lock_blockers = evaluate_locked_rule_blockers(
        schedule_rules,
        solver_input.locked_assignments,
        solver_input.participants,
    )
    if lock_blockers:
        blocked_evaluation = blocked_generation_rule_evaluation(
            schedule_rules,
            lock_blockers,
        )
        run.status = "FAILED"
        run.duration_ms = 0
        run.rule_evaluation = blocked_evaluation
        run.diagnostics = {"ruleBlockers": blocked_evaluation}
        run.finished_at = utc_now()
        db.commit()
        raise AppError(
            422,
            "SCHEDULE_RULES_BLOCKED",
            "当前锁定安排与本次排表要求冲突",
            details={"ruleEvaluation": blocked_evaluation},
        )

    started = time.perf_counter()
    try:
        result = solve(solver_input)
    except (ValueError, RuntimeError) as exc:
        stored_run = db.get(GenerationRun, run.id)
        if stored_run is not None:
            stored_run.status = "FAILED"
            stored_run.duration_ms = round((time.perf_counter() - started) * 1000)
            stored_run.diagnostics = {"error": str(exc)}
            stored_run.finished_at = utc_now()
            db.commit()
        raise AppError(422, "SCHEDULE_GENERATION_FAILED", f"自动排表失败：{exc}") from exc

    require_edit_lock(db, schedule_id, current_user.id, request.state.edit_lock_token)
    current = _load_schedule(db, schedule_id, for_update=True)
    stored_run = db.get(GenerationRun, run.id)
    if stored_run is None:
        raise AppError(500, "GENERATION_RUN_MISSING", "生成记录不存在")
    stored_run.duration_ms = round((time.perf_counter() - started) * 1000)
    stored_run.finished_at = utc_now()
    stored_run.objective_summary = objective_summary_payload(result, solver_input.dungeon.formula)
    stored_run.diagnostics = solver_diagnostics_payload(result)
    if current.revision != payload.base_revision:
        stored_run.status = "STALE"
        db.commit()
        raise AppError(
            409,
            "SCHEDULE_GENERATION_STALE",
            "求解期间排表已发生变化，请重新生成",
            details={"expected": payload.base_revision, "current": current.revision},
        )
    if result.status in (SolverStatus.INFEASIBLE, SolverStatus.ERROR):
        stored_run.status = "FAILED"
        stored_run.rule_evaluation = blocked_generation_rule_evaluation(schedule_rules)
        db.commit()
        raise AppError(
            422,
            "SCHEDULE_GENERATION_INFEASIBLE",
            "当前锁定、候选角色或规则无法生成有效排表",
            details={"ruleEvaluation": stored_run.rule_evaluation},
        )
    stored_run.rule_evaluation = evaluate_compiled_rules(
        schedule_rules, result.assignments, solver_input.participants
    )

    try:
        clear_regeneratable_assignments(
            current,
            solver_input,
            preserve_locks=payload.preserve_locks,
        )
        db.flush()
        diagnostics = apply_solver_result(
            current,
            solver_input,
            result,
        )
    except ValueError as exc:
        db.rollback()
        stored_run = db.get(GenerationRun, run.id)
        if stored_run is None:
            raise AppError(500, "GENERATION_RUN_MISSING", "生成记录不存在") from exc
        stored_run.status = "FAILED"
        stored_run.diagnostics = {**(stored_run.diagnostics or {}), "applyError": str(exc)}
        stored_run.duration_ms = round((time.perf_counter() - started) * 1000)
        stored_run.finished_at = utc_now()
        db.commit()
        raise AppError(422, "SCHEDULE_GENERATION_APPLY_FAILED", str(exc)) from exc
    current.revision += 1
    current.updated_by = current_user.id
    current.updated_at = utc_now()
    current.status = "DRAFT"
    current.validation_summary = {
        "error": 0,
        "warning": sum(issue.severity == "WARNING" for issue in result.issues),
        "info": len(result.unassigned),
    }
    stored_run.status = "PARTIAL" if result.status == SolverStatus.PARTIAL else "SUCCEEDED"
    stored_run.result_revision = current.revision
    stored_run.diagnostics = diagnostics
    db.commit()

    refreshed = _load_schedule(db, schedule_id)
    refreshed_run = db.get(GenerationRun, run.id)
    if refreshed_run is None:
        raise AppError(500, "GENERATION_RUN_MISSING", "生成记录不存在")
    return GenerationResponse(
        run=GenerationRunView.model_validate(refreshed_run),
        schedule=ScheduleDetail.model_validate(refreshed),
    )


@router.get(
    "/schedules/{schedule_id}/generation-runs",
    response_model=GenerationRunList,
)
def list_generation_runs(
    schedule_id: uuid.UUID, db: DbSession, current_user: ScheduleReader
) -> GenerationRunList:
    del current_user
    if db.get(Schedule, schedule_id) is None:
        raise AppError(404, "SCHEDULE_NOT_FOUND", "排表不存在")
    runs = list(
        db.scalars(
            select(GenerationRun)
            .where(GenerationRun.schedule_id == schedule_id)
            .order_by(GenerationRun.created_at.desc())
        )
    )
    db.commit()
    return GenerationRunList(
        items=[GenerationRunView.model_validate(run) for run in runs], total=len(runs)
    )


@router.get("/generation-runs/{run_id}", response_model=GenerationRunView)
def get_generation_run(
    run_id: uuid.UUID, db: DbSession, current_user: ScheduleReader
) -> GenerationRunView:
    del current_user
    run = db.get(GenerationRun, run_id)
    if run is None:
        raise AppError(404, "GENERATION_RUN_NOT_FOUND", "生成记录不存在")
    db.commit()
    return GenerationRunView.model_validate(run)
