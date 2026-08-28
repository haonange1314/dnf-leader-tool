from app.application.schedule_generation import objective_summary_payload
from app.schemas.dungeon import FormulaDefinition
from app.solver.models import ObjectiveSummary, SolverResult, SolverStatus


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
    )

    payload = objective_summary_payload(
        result,
        FormulaDefinition(code="TEST", version=1, damage_scale=100, buffer_scale=10),
    )

    assert payload["damageSpreadDisplay"] == "57.5"
    assert payload["bufferSpreadDisplay"] == "2.9"
