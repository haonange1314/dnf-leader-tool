from app.application.schedule_generation import (
    objective_summary_payload,
    solver_diagnostics_payload,
)
from app.schemas.dungeon import FormulaDefinition
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
