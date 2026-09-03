import uuid
from types import SimpleNamespace

import pytest

from app.api.v1.routes import generation as generation_routes
from app.application.schedule_generation import (
    objective_summary_payload,
    solver_diagnostics_payload,
)
from app.core.errors import AppError
from app.schemas.dungeon import FormulaDefinition
from app.schemas.schedule import GenerationRequest
from app.solver.models import (
    ObjectiveStageOutcome,
    ObjectiveStageResult,
    ObjectiveSummary,
    SolverResult,
    SolverStatus,
)


def test_objective_summary_uses_formula_scales_for_display_values() -> None:
    result = SolverResult(
        status=SolverStatus.OPTIMAL,
        assignments=(),
        special_assignments=(),
        unassigned_participant_ids=(),
        unassigned=(),
        team_summaries=(),
        issues=(),
        objective_summary=ObjectiveSummary(
            assigned_count=12,
            participant_count=12,
            complete_wave_count=1,
            complete_team_count=3,
            preferred_composition_count=3,
            special_rule_satisfied_count=1,
            damage_spread=5750,
            buffer_spread=29,
            strength_order_violation_count=0,
        ),
        objective_value=0,
        wall_time_seconds=0.1,
        objective_stages=(
            ObjectiveStageResult(
                code="ASSIGNED_COUNT",
                value=12,
                outcome=ObjectiveStageOutcome.TARGET_REACHED,
                duration_seconds=0.0084,
            ),
        ),
    )

    payload = objective_summary_payload(
        result,
        FormulaDefinition(code="TEST", version=1, damage_scale=100, buffer_scale=10),
    )

    assert payload["damageSpreadDisplay"] == "57.5"
    assert payload["bufferSpreadDisplay"] == "2.9"

    diagnostics = solver_diagnostics_payload(result)
    assert diagnostics["objectiveStages"] == [
        {
            "code": "ASSIGNED_COUNT",
            "value": 12,
            "outcome": "TARGET_REACHED",
            "durationMs": 8,
        }
    ]


def test_generation_invalidates_a_stale_active_rule_context(monkeypatch) -> None:
    rule_set_id = uuid.uuid4()
    schedule = SimpleNamespace(
        id=uuid.uuid4(),
        revision=4,
        status="DRAFT",
        active_rule_set_id=rule_set_id,
        active_rule_set=SimpleNamespace(status="CONFIRMED"),
        updated_by=None,
        updated_at=None,
        validation_summary={"errorCount": 0},
    )
    committed = False

    class FakeDb:
        def commit(self) -> None:
            nonlocal committed
            committed = True

    monkeypatch.setattr(
        generation_routes,
        "_load_schedule",
        lambda *_args, **_kwargs: schedule,
    )
    monkeypatch.setattr(
        generation_routes,
        "active_rule_set_context_is_current",
        lambda _schedule: False,
    )

    with pytest.raises(AppError) as error:
        generation_routes.generate_schedule(
            schedule.id,
            GenerationRequest(base_revision=4, expected_rule_set_id=rule_set_id),
            SimpleNamespace(state=SimpleNamespace()),
            FakeDb(),
            SimpleNamespace(id=uuid.uuid4()),
        )

    assert error.value.code == "RULE_SET_CONTEXT_STALE"
    assert committed
    assert schedule.revision == 5
    assert schedule.active_rule_set.status == "STALE"
    assert schedule.active_rule_set_id is None
    assert schedule.validation_summary is None
