from collections import defaultdict

from ortools.sat.python import cp_model

from app.domain.schedule import MAX_SCHEDULE_POSITIONS, MAX_WAVE_COUNT
from app.schemas.dungeon import RoleType
from app.solver.models import (
    ObjectiveStageOutcome,
    ObjectiveStageResult,
    ObjectiveSummary,
    SolverAssignment,
    SolverInput,
    SolverIssue,
    SolverResult,
    SolverStatus,
    SpecialAssignment,
    TeamSummary,
    UnassignedReason,
)

INT64_MAX = (1 << 63) - 1


def solve(solver_input: SolverInput) -> SolverResult:
    _validate_input(solver_input)
    model = cp_model.CpModel()
    participants = solver_input.participants
    teams = solver_input.dungeon.teams
    waves = range(1, solver_input.wave_count + 1)
    team_index_by_key = {team.team_key: index for index, team in enumerate(teams)}
    participant_index_by_id = {
        participant.participant_id: index for index, participant in enumerate(participants)
    }
    locked_empty_counts: dict[tuple[int, str], int] = defaultdict(int)
    for locked_empty in solver_input.locked_empty_slots:
        locked_empty_counts[locked_empty.wave_no, locked_empty.team_key] += locked_empty.count

    x: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for participant_index, participant in enumerate(participants):
        allowed = set(waves if participant.allowed_waves is None else participant.allowed_waves)
        for wave_no in waves:
            for team_index, team in enumerate(teams):
                variable = model.new_bool_var(f"x_{participant_index}_{wave_no}_{team_index}")
                x[participant_index, wave_no, team_index] = variable
                if wave_no not in allowed:
                    model.add(variable == 0)
                if (
                    participant.allowed_team_keys is not None
                    and team.team_key not in participant.allowed_team_keys
                ):
                    model.add(variable == 0)

    for locked in solver_input.locked_assignments:
        model.add(
            x[
                participant_index_by_id[locked.participant_id],
                locked.wave_no,
                team_index_by_key[locked.team_key],
            ]
            == 1
        )

    assigned: list[cp_model.IntVar] = []
    for participant_index, _participant in enumerate(participants):
        variable = model.new_bool_var(f"assigned_{participant_index}")
        model.add(
            variable
            == sum(
                x[participant_index, wave_no, team_index]
                for wave_no in waves
                for team_index, _team in enumerate(teams)
            )
        )
        assigned.append(variable)

    participant_indices_by_player: dict[str, list[int]] = defaultdict(list)
    for participant_index, participant in enumerate(participants):
        participant_indices_by_player[participant.player_id].append(participant_index)
    preference_by_player = {
        preference.player_id: preference for preference in solver_input.player_preferences
    }
    player_assignment_upper_bound = 0
    for player_id, indices in participant_indices_by_player.items():
        for wave_no in waves:
            model.add(
                sum(
                    x[participant_index, wave_no, team_index]
                    for participant_index in indices
                    for team_index, _team in enumerate(teams)
                )
                <= 1
            )
        allowed_waves: set[int] = set()
        for participant_index in indices:
            participant_allowed_waves = participants[participant_index].allowed_waves
            allowed_waves.update(
                waves
                if participant_allowed_waves is None
                else participant_allowed_waves
            )
        player_capacity = min(len(indices), len(allowed_waves))
        preference = preference_by_player.get(player_id)
        if preference is not None and preference.max_wave_count is not None:
            player_capacity = min(player_capacity, preference.max_wave_count)
        model.add(
            sum(assigned[participant_index] for participant_index in indices)
            <= player_capacity
        )
        player_assignment_upper_bound += player_capacity

    preference_penalties: list[cp_model.LinearExpr] = []
    for player_id, indices in participant_indices_by_player.items():
        preference = preference_by_player.get(player_id)
        if preference is None:
            continue
        player_wave: dict[int, cp_model.IntVar] = {}
        for wave_no in waves:
            used = model.new_bool_var(f"player_wave_{player_id}_{wave_no}")
            model.add(
                used
                == sum(
                    x[participant_index, wave_no, team_index]
                    for participant_index in indices
                    for team_index, _team in enumerate(teams)
                )
            )
            player_wave[wave_no] = used
        assigned_count = cp_model.LinearExpr.sum(list(player_wave.values()))
        if preference.max_wave_count is not None:
            model.add(assigned_count <= preference.max_wave_count)
        if not solver_input.dungeon.optimization_rules.respect_player_preferences:
            continue
        if preference.prefer_early:
            preference_penalties.append(
                cp_model.LinearExpr.sum([wave_no * used for wave_no, used in player_wave.items()])
            )
        if preference.prefer_contiguous and len(player_wave) > 1:
            any_used = model.new_bool_var(f"player_any_{player_id}")
            model.add_max_equality(any_used, list(player_wave.values()))
            latest = model.new_int_var(0, solver_input.wave_count, f"player_latest_{player_id}")
            model.add_max_equality(
                latest, [wave_no * used for wave_no, used in player_wave.items()]
            )
            earliest_candidates: list[cp_model.IntVar] = []
            for wave_no, used in player_wave.items():
                candidate = model.new_int_var(
                    1,
                    solver_input.wave_count * 2 + 1,
                    f"player_earliest_candidate_{player_id}_{wave_no}",
                )
                model.add(candidate == wave_no + (solver_input.wave_count + 1) * (1 - used))
                earliest_candidates.append(candidate)
            earliest = model.new_int_var(
                1, solver_input.wave_count * 2 + 1, f"player_earliest_{player_id}"
            )
            model.add_min_equality(earliest, earliest_candidates)
            gap = model.new_int_var(0, solver_input.wave_count, f"player_gap_{player_id}")
            model.add(gap == latest - earliest + 1 - assigned_count).only_enforce_if(any_used)
            model.add(gap == 0).only_enforce_if(~any_used)
            preference_penalties.append(gap)

    team_full: dict[tuple[int, int], cp_model.IntVar] = {}
    selected_composition: dict[tuple[int, int, int], cp_model.IntVar] = {}
    composition_rules = solver_input.dungeon.composition_rules.allowed
    for wave_no in waves:
        for team_index, team in enumerate(teams):
            member_count = sum(
                x[participant_index, wave_no, team_index]
                for participant_index, _participant in enumerate(participants)
            )
            effective_capacity = team.member_count - locked_empty_counts[wave_no, team.team_key]
            model.add(member_count <= effective_capacity)
            full = model.new_bool_var(f"team_full_{wave_no}_{team_index}")
            model.add(member_count == team.member_count).only_enforce_if(full)
            model.add(member_count <= team.member_count - 1).only_enforce_if(~full)
            team_full[wave_no, team_index] = full

            applicable = [
                (rule_index, rule)
                for rule_index, rule in enumerate(composition_rules)
                if team.team_key in rule.applicable_team_keys
            ]
            selections: list[cp_model.IntVar] = []
            for rule_index, rule in applicable:
                selection = model.new_bool_var(f"composition_{wave_no}_{team_index}_{rule_index}")
                selected_composition[wave_no, team_index, rule_index] = selection
                selections.append(selection)
                for role_type in RoleType:
                    role_count = sum(
                        x[participant_index, wave_no, team_index]
                        for participant_index, participant in enumerate(participants)
                        if participant.role_type == role_type
                    )
                    model.add(role_count == rule.roles.get(role_type, 0)).only_enforce_if(selection)
            model.add(sum(selections) == full)

    wave_full: dict[int, cp_model.IntVar] = {}
    for wave_no in waves:
        full = model.new_bool_var(f"wave_full_{wave_no}")
        full_teams = [team_full[wave_no, team_index] for team_index, _ in enumerate(teams)]
        model.add_bool_and(full_teams).only_enforce_if(full)
        model.add_bool_or([~team_full_var for team_full_var in full_teams]).only_enforce_if(~full)
        wave_full[wave_no] = full

    special_variables: dict[tuple[int, int, int], cp_model.IntVar] = {}
    special_satisfied: list[cp_model.IntVar] = []
    for rule_index, special_rule in enumerate(solver_input.dungeon.special_role_rules.rules):
        target_team_index = team_index_by_key[special_rule.target_team_key]
        eligible_indices = [
            participant_index
            for participant_index, participant in enumerate(participants)
            if participant.is_treasure_damage and participant.role_type == RoleType.DAMAGE
        ]
        for wave_no in waves:
            variables: list[cp_model.IntVar] = []
            for participant_index in eligible_indices:
                variable = model.new_bool_var(f"special_{rule_index}_{participant_index}_{wave_no}")
                model.add(variable <= x[participant_index, wave_no, target_team_index])
                special_variables[rule_index, participant_index, wave_no] = variable
                variables.append(variable)
            special_count = cp_model.LinearExpr.sum(variables)
            model.add(special_count <= special_rule.count_per_wave)
            satisfied = model.new_bool_var(f"special_satisfied_{rule_index}_{wave_no}")
            model.add(special_count == special_rule.count_per_wave * satisfied)
            model.add(satisfied <= wave_full[wave_no])
            special_satisfied.append(satisfied)

    total_score = sum(participant.score for participant in participants)
    early_terms: list[cp_model.LinearExpr] = []
    assigned_by_wave: dict[int, cp_model.LinearExpr] = {}
    for participant_index, _participant in enumerate(participants):
        for wave_no in waves:
            early_weight = solver_input.wave_count - wave_no + 1
            team_assignments = [
                x[participant_index, wave_no, team_index] for team_index, _team in enumerate(teams)
            ]
            if solver_input.dungeon.missing_slot_policy.mode == "FILL_EARLIER_WAVES":
                early_terms.append(early_weight * cp_model.LinearExpr.sum(team_assignments))
    for wave_no in waves:
        assigned_by_wave[wave_no] = cp_model.LinearExpr.sum(
            [
                x[participant_index, wave_no, team_index]
                for participant_index, _participant in enumerate(participants)
                for team_index, _team in enumerate(teams)
            ]
        )

    spread_objective: cp_model.IntVar | None = None
    if solver_input.dungeon.missing_slot_policy.mode == "SPREAD_EVENLY":
        maximum_wave_fill = model.new_int_var(
            0, solver_input.dungeon.participants_per_wave, "wave_fill_max"
        )
        minimum_wave_fill = model.new_int_var(
            0, solver_input.dungeon.participants_per_wave, "wave_fill_min"
        )
        spread_objective = model.new_int_var(
            0, solver_input.dungeon.participants_per_wave, "wave_fill_spread"
        )
        model.add_max_equality(maximum_wave_fill, list(assigned_by_wave.values()))
        model.add_min_equality(minimum_wave_fill, list(assigned_by_wave.values()))
        model.add(spread_objective == maximum_wave_fill - minimum_wave_fill)

    composition_penalties = [
        (composition_rules[rule_index].priority - 1) * variable
        for (_wave_no, _team_index, rule_index), variable in selected_composition.items()
    ]

    metric_totals: dict[tuple[RoleType, int, int], cp_model.IntVar] = {}
    score_upper_bound = total_score
    for metric in RoleType:
        for wave_no in waves:
            for team_index, _team in enumerate(teams):
                total = model.new_int_var(
                    0, score_upper_bound, f"{metric.value.lower()}_{wave_no}_{team_index}"
                )
                model.add(
                    total
                    == sum(
                        participant.score * x[participant_index, wave_no, team_index]
                        for participant_index, participant in enumerate(participants)
                        if participant.role_type == metric
                    )
                )
                metric_totals[metric, wave_no, team_index] = total

    strength_order_penalties: list[cp_model.LinearExpr] = []
    strength_order_pairs: list[
        tuple[int, cp_model.LinearExpr, cp_model.LinearExpr]
    ] = []
    for order_index, order in enumerate(solver_input.dungeon.strength_order_rules.orders):
        for wave_no in waves:
            for pair_index, (stronger_key, weaker_key) in enumerate(
                zip(order.teams, order.teams[1:], strict=False)
            ):
                stronger = metric_totals[order.metric, wave_no, team_index_by_key[stronger_key]]
                weaker = metric_totals[order.metric, wave_no, team_index_by_key[weaker_key]]
                slack = model.new_int_var(
                    0,
                    score_upper_bound,
                    f"strength_order_slack_{order_index}_{wave_no}_{pair_index}",
                )
                model.add(slack >= weaker - stronger).only_enforce_if(wave_full[wave_no])
                model.add(slack == 0).only_enforce_if(~wave_full[wave_no])
                strength_order_penalties.append(slack)
                strength_order_pairs.append((wave_no, stronger, weaker))

    balance_penalties: list[tuple[RoleType, cp_model.LinearExpr]] = []
    for metric in solver_input.dungeon.optimization_rules.balance_across_waves:
        wave_totals: dict[int, cp_model.LinearExpr] = {}
        for wave_no in waves:
            wave_totals[wave_no] = cp_model.LinearExpr.sum(
                [
                    metric_totals[metric, wave_no, team_index]
                    for team_index, _team in enumerate(teams)
                ]
            )
        maximum = model.new_int_var(0, score_upper_bound, f"{metric.value}_wave_max")
        minimum = model.new_int_var(0, score_upper_bound, f"{metric.value}_wave_min")
        spread = model.new_int_var(0, score_upper_bound, f"{metric.value}_wave_spread")
        model.add(maximum >= minimum)
        model.add(spread == maximum - minimum)
        for wave_no in waves:
            model.add(maximum >= wave_totals[wave_no]).only_enforce_if(wave_full[wave_no])
            model.add(minimum <= wave_totals[wave_no]).only_enforce_if(wave_full[wave_no])
        balance_penalties.append((metric, spread))

    companion_penalties: list[cp_model.LinearExpr] = []
    for rule_index, special_rule in enumerate(solver_input.dungeon.special_role_rules.rules):
        if (
            special_rule.companion_policy is None
            or special_rule.companion_policy.objective != "MINIMIZE_OTHER_MEMBER_SCORE"
        ):
            continue
        target_team_index = team_index_by_key[special_rule.target_team_key]
        for wave_no in waves:
            target_damage = cp_model.LinearExpr.sum(
                [
                    participant.score * x[participant_index, wave_no, target_team_index]
                    for participant_index, participant in enumerate(participants)
                    if participant.role_type == special_rule.companion_policy.role_type
                ]
            )
            selected_core_score = cp_model.LinearExpr.sum(
                [
                    participants[participant_index].score * variable
                    for (
                        candidate_rule,
                        participant_index,
                        candidate_wave,
                    ), variable in special_variables.items()
                    if candidate_rule == rule_index and candidate_wave == wave_no
                ]
            )
            companion_penalties.append(target_damage - selected_core_score)

    assigned_total = cp_model.LinearExpr.sum(assigned)
    position_assignment_upper_bound = min(
        len(participants),
        solver_input.wave_count * solver_input.dungeon.participants_per_wave,
    )
    assignment_upper_bound = min(
        position_assignment_upper_bound,
        player_assignment_upper_bound,
    )
    model.add(assigned_total <= assignment_upper_bound)
    hint_variables = [*x.values(), *special_variables.values()]
    elapsed = 0.0
    objective_stages: list[ObjectiveStageResult] = []
    stage_value_objectives: dict[str, cp_model.LinearExpr] = {}
    all_stage_outcomes_optimal = True

    def record_stage(
        code: str,
        stage_solver: cp_model.CpSolver,
        stage_status: SolverStatus,
        value: int,
        *,
        target_reached: bool,
        duration_seconds: float | None = None,
    ) -> None:
        nonlocal all_stage_outcomes_optimal
        outcome = (
            ObjectiveStageOutcome.OPTIMAL
            if stage_status == SolverStatus.OPTIMAL
            else ObjectiveStageOutcome.TARGET_REACHED
            if target_reached
            else ObjectiveStageOutcome.FEASIBLE
        )
        if outcome == ObjectiveStageOutcome.FEASIBLE:
            all_stage_outcomes_optimal = False
        objective_stages.append(
            ObjectiveStageResult(
                code=code,
                value=value,
                outcome=outcome,
                duration_seconds=(
                    stage_solver.wall_time
                    if duration_seconds is None
                    else duration_seconds
                ),
            )
    )

    availability_budget = _stage_budget(solver_input.time_limit_seconds, 0.30)
    if player_assignment_upper_bound < position_assignment_upper_bound:
        target_model = model.clone()
        target_model.add(assigned_total == assignment_upper_bound)
        availability_solver, availability_status = _solve_stage(
            target_model,
            assigned_total,
            maximize=True,
            time_limit_seconds=availability_budget * 0.75,
            random_seed=solver_input.random_seed,
        )
        availability_elapsed = availability_solver.wall_time
    else:
        availability_solver, availability_status = _solve_stage(
            model,
            assigned_total,
            maximize=True,
            time_limit_seconds=availability_budget,
            random_seed=solver_input.random_seed,
        )
        availability_elapsed = availability_solver.wall_time
    if availability_status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        availability_solver, availability_status = _solve_stage(
            model,
            assigned_total,
            maximize=True,
            time_limit_seconds=max(0.05, availability_budget - availability_elapsed),
            random_seed=solver_input.random_seed,
        )
        availability_elapsed += availability_solver.wall_time
    elapsed += availability_elapsed
    best_solver = availability_solver
    if availability_status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return SolverResult(
            status=availability_status,
            assignments=(),
            special_assignments=(),
            unassigned_participant_ids=tuple(p.participant_id for p in participants),
            unassigned=tuple(
                UnassignedReason(
                    participant_id=p.participant_id,
                    code="UNASSIGNED_ROLE_COMPOSITION",
                    message_params={},
                )
                for p in participants
            ),
            team_summaries=(),
            issues=(),
            objective_summary=ObjectiveSummary(0, len(participants), 0, 0, 0, 0, 0, 0, 0),
            objective_value=None,
            wall_time_seconds=availability_solver.wall_time,
        )

    best_assigned_count = round(availability_solver.value(assigned_total))
    record_stage(
        "ASSIGNED_COUNT",
        availability_solver,
        availability_status,
        best_assigned_count,
        target_reached=best_assigned_count == assignment_upper_bound,
        duration_seconds=availability_elapsed,
    )
    model.add(assigned_total == best_assigned_count)
    _replace_hints(model, hint_variables, availability_solver)

    def canonical_stage_value(
        code: str,
        stage_solver: cp_model.CpSolver,
        objective: cp_model.LinearExpr,
    ) -> int:
        if code == "STRENGTH_ORDER":
            return sum(
                max(
                    0,
                    round(stage_solver.value(weaker))
                    - round(stage_solver.value(stronger)),
                )
                for wave_no, stronger, weaker in strength_order_pairs
                if stage_solver.value(wave_full[wave_no])
            )
        if code.startswith("BALANCE_"):
            metric = RoleType(code.removeprefix("BALANCE_"))
            complete_wave_totals = [
                sum(
                    round(stage_solver.value(metric_totals[metric, wave_no, team_index]))
                    for team_index, _team in enumerate(teams)
                )
                for wave_no in waves
                if stage_solver.value(wave_full[wave_no])
            ]
            return (
                max(complete_wave_totals) - min(complete_wave_totals)
                if complete_wave_totals
                else 0
            )
        return round(stage_solver.value(objective))

    def optimize_and_fix_stage(
        code: str,
        objective: cp_model.LinearExpr,
        *,
        maximize: bool,
        budget_ratio: float,
        target_value: int,
        value_objective: cp_model.LinearExpr | None = None,
    ) -> None:
        nonlocal elapsed, best_solver
        evaluated_objective = value_objective if value_objective is not None else objective
        stage_value_objectives[code] = evaluated_objective
        stage_solver, stage_status = _solve_stage(
            model,
            objective,
            maximize=maximize,
            time_limit_seconds=_stage_budget(solver_input.time_limit_seconds, budget_ratio),
            random_seed=solver_input.random_seed,
        )
        elapsed += stage_solver.wall_time
        if stage_status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
            best_solver = stage_solver
            stage_value = round(stage_solver.value(evaluated_objective))
            _replace_hints(model, hint_variables, stage_solver)
            recorded_status = stage_status
        else:
            stage_value = canonical_stage_value(code, best_solver, evaluated_objective)
            recorded_status = SolverStatus.FEASIBLE
        record_stage(
            code,
            stage_solver,
            recorded_status,
            stage_value,
            target_reached=stage_value == target_value,
        )
        model.add(evaluated_objective == stage_value)

    if spread_objective is not None:
        optimize_and_fix_stage(
            "WAVE_FILL_SPREAD",
            spread_objective,
            maximize=False,
            budget_ratio=0.05,
            target_value=0,
        )

    early_objective = cp_model.LinearExpr.sum(early_terms)
    complete_multiplier = len(team_full) + 1
    complete_objective = complete_multiplier * cp_model.LinearExpr.sum(
        list(wave_full.values())
    ) + cp_model.LinearExpr.sum(list(team_full.values()))
    complete_upper_bound = _complete_objective_upper_bound(
        best_assigned_count,
        solver_input.wave_count,
        tuple(team.member_count for team in teams),
        complete_multiplier,
    )
    early_upper_bound = _early_fill_upper_bound(
        best_assigned_count,
        solver_input.wave_count,
        solver_input.dungeon.participants_per_wave,
    )
    complete_search_objective = complete_objective
    complete_search_upper_bound = complete_upper_bound
    if early_terms and complete_search_upper_bound <= (
        INT64_MAX - early_upper_bound
    ) // (early_upper_bound + 1):
        # This bounded tie-break keeps completeness strictly dominant while
        # removing equivalent wave permutations from the search space.
        complete_search_objective = (
            (early_upper_bound + 1) * complete_objective + early_objective
        )
        complete_search_upper_bound = (
            (early_upper_bound + 1) * complete_search_upper_bound + early_upper_bound
        )
    special_total = cp_model.LinearExpr.sum(special_satisfied)
    if special_satisfied and complete_search_upper_bound <= (
        INT64_MAX - len(special_satisfied)
    ) // (len(special_satisfied) + 1):
        # A second bounded tie-break gives later special-role optimization a
        # useful incumbent without changing the fixed stage priorities.
        complete_search_objective = (
            (len(special_satisfied) + 1) * complete_search_objective + special_total
        )
    optimize_and_fix_stage(
        "COMPLETENESS",
        complete_search_objective,
        maximize=True,
        budget_ratio=0.15,
        target_value=complete_upper_bound,
        value_objective=complete_objective,
    )

    if early_terms:
        optimize_and_fix_stage(
            "EARLY_FILL",
            early_objective,
            maximize=True,
            budget_ratio=0.05,
            target_value=early_upper_bound,
        )

    composition_penalty = cp_model.LinearExpr.sum(composition_penalties)
    optimize_and_fix_stage(
        "COMPOSITION_PRIORITY",
        composition_penalty,
        maximize=False,
        budget_ratio=0.10,
        target_value=0,
    )

    if special_satisfied:
        maximum_complete_waves = min(
            solver_input.wave_count,
            best_assigned_count // solver_input.dungeon.participants_per_wave,
        )
        special_upper_bound = (
            len(solver_input.dungeon.special_role_rules.rules) * maximum_complete_waves
        )
        optimize_and_fix_stage(
            "SPECIAL_ROLE",
            special_total,
            maximize=True,
            budget_ratio=0.20,
            target_value=special_upper_bound,
        )

    final_stages: list[tuple[str, list[cp_model.LinearExpr], float]] = [
        ("STRENGTH_ORDER", strength_order_penalties, 0.10),
    ]
    balance_budget = 0.08 / max(1, len(balance_penalties))
    final_stages.extend(
        (f"BALANCE_{metric.value}", [penalty], balance_budget)
        for metric, penalty in balance_penalties
    )
    final_stages.extend(
        [
            ("SPECIAL_COMPANION", companion_penalties, 0.01),
            ("PLAYER_PREFERENCE", preference_penalties, 0.01),
        ]
    )
    for stage_code, penalties, budget_ratio in final_stages:
        if not penalties:
            continue
        stage_objective = cp_model.LinearExpr.sum(penalties)
        optimize_and_fix_stage(
            stage_code,
            stage_objective,
            maximize=False,
            budget_ratio=budget_ratio,
            target_value=0,
        )

    solver = best_solver
    status = SolverStatus.OPTIMAL if all_stage_outcomes_optimal else SolverStatus.FEASIBLE
    objective_stages = [
        ObjectiveStageResult(
            code=stage.code,
            value=canonical_stage_value(
                stage.code,
                solver,
                stage_value_objectives.get(stage.code, assigned_total),
            ),
            outcome=stage.outcome,
            duration_seconds=stage.duration_seconds,
        )
        for stage in objective_stages
    ]

    assignments: list[SolverAssignment] = []
    assigned_locations: dict[str, tuple[int, str]] = {}
    for participant_index, participant in enumerate(participants):
        for wave_no in waves:
            for team_index, team in enumerate(teams):
                if solver.value(x[participant_index, wave_no, team_index]):
                    assignments.append(
                        SolverAssignment(participant.participant_id, wave_no, team.team_key)
                    )
                    assigned_locations[participant.participant_id] = (wave_no, team.team_key)

    special_assignments: list[SpecialAssignment] = []
    for (rule_index, participant_index, wave_no), variable in special_variables.items():
        if solver.value(variable):
            special_rule = solver_input.dungeon.special_role_rules.rules[rule_index]
            special_assignments.append(
                SpecialAssignment(
                    special_rule.code,
                    participants[participant_index].participant_id,
                    wave_no,
                    special_rule.target_team_key,
                )
            )

    summaries = _summarize(solver_input, assignments)
    unassigned = tuple(
        participant.participant_id
        for participant in participants
        if participant.participant_id not in assigned_locations
    )
    unassigned_reasons = _diagnose_unassigned(solver_input, assignments, unassigned)
    objective_summary = _objective_summary(solver_input, summaries, special_assignments)
    issues = _solver_issues(solver_input, summaries, special_assignments)
    result_status = (
        SolverStatus.PARTIAL
        if unassigned or any(summary.composition_code is None for summary in summaries)
        else status
    )
    return SolverResult(
        status=result_status,
        assignments=tuple(assignments),
        special_assignments=tuple(special_assignments),
        unassigned_participant_ids=unassigned,
        unassigned=unassigned_reasons,
        team_summaries=summaries,
        issues=issues,
        objective_summary=objective_summary,
        objective_value=solver.objective_value,
        wall_time_seconds=elapsed,
        objective_stages=tuple(objective_stages),
    )


def _solve_stage(
    model: cp_model.CpModel,
    objective: cp_model.LinearExpr,
    *,
    maximize: bool,
    time_limit_seconds: float,
    random_seed: int,
) -> tuple[cp_model.CpSolver, SolverStatus]:
    if maximize:
        model.maximize(objective)
    else:
        model.minimize(objective)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.random_seed = random_seed
    solver.parameters.num_search_workers = 1
    return solver, _status(solver.solve(model))


def _replace_hints(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    solver: cp_model.CpSolver,
) -> None:
    model.clear_hints()  # type: ignore[no-untyped-call]
    for variable in variables:
        model.add_hint(variable, solver.value(variable))


def _stage_budget(total_seconds: float, share: float) -> float:
    return max(0.05, total_seconds * share)


def _early_fill_upper_bound(
    assigned_count: int, wave_count: int, participants_per_wave: int
) -> int:
    remaining = assigned_count
    upper_bound = 0
    for wave_no in range(1, wave_count + 1):
        filled = min(remaining, participants_per_wave)
        upper_bound += filled * (wave_count - wave_no + 1)
        remaining -= filled
        if remaining == 0:
            break
    return upper_bound


def _complete_objective_upper_bound(
    assigned_count: int,
    wave_count: int,
    team_capacities: tuple[int, ...],
    complete_multiplier: int,
) -> int:
    participants_per_wave = sum(team_capacities)
    complete_waves = min(wave_count, assigned_count // participants_per_wave)
    remaining = assigned_count - complete_waves * participants_per_wave
    additional_complete_teams = 0
    for capacity in sorted(team_capacities):
        if capacity > remaining:
            break
        additional_complete_teams += 1
        remaining -= capacity
    complete_teams = complete_waves * len(team_capacities) + additional_complete_teams
    return complete_multiplier * complete_waves + complete_teams


def _validate_input(solver_input: SolverInput) -> None:
    definition = solver_input.dungeon
    if solver_input.revision < 1:
        raise ValueError("revision 必须大于 0")
    if not 1 <= solver_input.wave_count <= MAX_WAVE_COUNT:
        raise ValueError(f"wave_count 必须位于 1..{MAX_WAVE_COUNT}")
    if solver_input.wave_count < definition.min_wave_count or (
        definition.max_wave_count is not None
        and solver_input.wave_count > definition.max_wave_count
    ):
        raise ValueError("wave_count 超出副本版本允许范围")
    if solver_input.wave_count * definition.participants_per_wave > MAX_SCHEDULE_POSITIONS:
        raise ValueError(f"排表总位置数不能超过 {MAX_SCHEDULE_POSITIONS}")
    if not 1 <= solver_input.time_limit_seconds <= 60:
        raise ValueError("time_limit_seconds 必须位于 1..60")
    if len({participant.participant_id for participant in solver_input.participants}) != len(
        solver_input.participants
    ):
        raise ValueError("participant_id 必须唯一")
    participant_ids = {participant.participant_id for participant in solver_input.participants}
    player_ids = {participant.player_id for participant in solver_input.participants}
    team_keys = {team.team_key for team in definition.teams}
    if len({preference.player_id for preference in solver_input.player_preferences}) != len(
        solver_input.player_preferences
    ):
        raise ValueError("player_preferences 中的 player_id 必须唯一")
    for preference in solver_input.player_preferences:
        if preference.player_id not in player_ids:
            raise ValueError("player_preferences 引用了未知玩家")
        if preference.max_wave_count is not None and not (
            1 <= preference.max_wave_count <= solver_input.wave_count
        ):
            raise ValueError("max_wave_count 超出排表波次范围")
    for participant in solver_input.participants:
        if not isinstance(participant.score, int) or isinstance(participant.score, bool):
            raise ValueError("score 必须是整数")
        if not 0 <= participant.score <= INT64_MAX:
            raise ValueError("score 必须位于有符号 64 位整数范围")
        if participant.is_treasure_damage and participant.role_type != RoleType.DAMAGE:
            raise ValueError("只有 DAMAGE 角色可以标记为秘宝 C")
        if participant.allowed_waves is not None:
            if len(participant.allowed_waves) != len(set(participant.allowed_waves)):
                raise ValueError("allowed_waves 不能重复")
            if any(
                wave_no < 1 or wave_no > solver_input.wave_count
                for wave_no in participant.allowed_waves
            ):
                raise ValueError("allowed_waves 包含越界波次")
        if participant.allowed_team_keys is not None:
            if not participant.allowed_team_keys:
                raise ValueError("allowed_team_keys 不能为空")
            if len(participant.allowed_team_keys) != len(set(participant.allowed_team_keys)):
                raise ValueError("allowed_team_keys 不能重复")
            if not set(participant.allowed_team_keys) <= team_keys:
                raise ValueError("allowed_team_keys 引用了未知队伍")

    team_by_key = {team.team_key: team for team in definition.teams}
    locked_participants: set[str] = set()
    for locked in solver_input.locked_assignments:
        if locked.participant_id not in participant_ids:
            raise ValueError("locked_assignments 引用了未知角色")
        if locked.participant_id in locked_participants:
            raise ValueError("同一角色不能存在多个锁定安排")
        if locked.team_key not in team_by_key:
            raise ValueError("locked_assignments 引用了未知队伍")
        if not 1 <= locked.wave_no <= solver_input.wave_count:
            raise ValueError("locked_assignments 包含越界波次")
        participant = next(
            item
            for item in solver_input.participants
            if item.participant_id == locked.participant_id
        )
        if (
            participant.allowed_waves is not None
            and locked.wave_no not in participant.allowed_waves
        ):
            raise ValueError("锁定安排不在玩家可用波次内")
        locked_participants.add(locked.participant_id)
    empty_by_team: dict[tuple[int, str], int] = defaultdict(int)
    for locked_empty in solver_input.locked_empty_slots:
        if locked_empty.team_key not in team_by_key:
            raise ValueError("locked_empty_slots 引用了未知队伍")
        if not 1 <= locked_empty.wave_no <= solver_input.wave_count:
            raise ValueError("locked_empty_slots 包含越界波次")
        if locked_empty.count <= 0:
            raise ValueError("locked_empty_slots.count 必须大于 0")
        key = (locked_empty.wave_no, locked_empty.team_key)
        empty_by_team[key] += locked_empty.count
        if empty_by_team[key] > team_by_key[locked_empty.team_key].member_count:
            raise ValueError("锁定空位数不能超过队伍容量")

    total_score = sum(participant.score for participant in solver_input.participants)
    if total_score > INT64_MAX:
        raise ValueError("参与角色总评分超过有符号 64 位整数范围")
    strength_slack_count = sum(
        max(0, len(order.teams) - 1) * solver_input.wave_count
        for order in definition.strength_order_rules.orders
    )
    final_penalty_count = strength_slack_count + len(
        definition.optimization_rules.balance_across_waves
    )
    if final_penalty_count and total_score > INT64_MAX // final_penalty_count:
        raise ValueError("求解目标的最坏情况超过有符号 64 位整数范围")


def _status(status_code: cp_model.CpSolverStatus) -> SolverStatus:
    if status_code == cp_model.OPTIMAL:
        return SolverStatus.OPTIMAL
    if status_code == cp_model.FEASIBLE:
        return SolverStatus.FEASIBLE
    if status_code == cp_model.INFEASIBLE:
        return SolverStatus.INFEASIBLE
    return SolverStatus.ERROR


def _summarize(
    solver_input: SolverInput, assignments: list[SolverAssignment]
) -> tuple[TeamSummary, ...]:
    participant_by_id = {p.participant_id: p for p in solver_input.participants}
    assigned_by_team: dict[tuple[int, str], list[str]] = defaultdict(list)
    for assignment in assignments:
        assigned_by_team[assignment.wave_no, assignment.team_key].append(assignment.participant_id)

    summaries: list[TeamSummary] = []
    for wave_no in range(1, solver_input.wave_count + 1):
        for team in solver_input.dungeon.teams:
            members = [
                participant_by_id[participant_id]
                for participant_id in assigned_by_team[wave_no, team.team_key]
            ]
            role_counts = {
                role_type: sum(member.role_type == role_type for member in members)
                for role_type in RoleType
            }
            composition_code = next(
                (
                    rule.code
                    for rule in solver_input.dungeon.composition_rules.allowed
                    if team.team_key in rule.applicable_team_keys
                    and all(role_counts[role] == rule.roles.get(role, 0) for role in RoleType)
                ),
                None,
            )
            summaries.append(
                TeamSummary(
                    wave_no=wave_no,
                    team_key=team.team_key,
                    member_count=len(members),
                    role_counts=role_counts,
                    damage_total=sum(
                        member.score for member in members if member.role_type == RoleType.DAMAGE
                    ),
                    buffer_total=sum(
                        member.score for member in members if member.role_type == RoleType.BUFFER
                    ),
                    composition_code=composition_code,
                )
            )
    return tuple(summaries)


def _diagnose_unassigned(
    solver_input: SolverInput,
    assignments: list[SolverAssignment],
    unassigned_ids: tuple[str, ...],
) -> tuple[UnassignedReason, ...]:
    participant_by_id = {
        participant.participant_id: participant for participant in solver_input.participants
    }
    assigned_by_player: dict[str, list[SolverAssignment]] = defaultdict(list)
    for assignment in assignments:
        participant = participant_by_id[assignment.participant_id]
        assigned_by_player[participant.player_id].append(assignment)
    preferences = {
        preference.player_id: preference for preference in solver_input.player_preferences
    }
    capacity = solver_input.wave_count * solver_input.dungeon.participants_per_wave
    reasons: list[UnassignedReason] = []
    for participant_id in unassigned_ids:
        participant = participant_by_id[participant_id]
        allowed = (
            tuple(range(1, solver_input.wave_count + 1))
            if participant.allowed_waves is None
            else participant.allowed_waves
        )
        preference = preferences.get(participant.player_id)
        player_assignments = assigned_by_player[participant.player_id]
        if not allowed:
            code = "UNASSIGNED_NO_AVAILABLE_WAVE"
            params: dict[str, object] = {"allowedWaves": []}
        elif (
            preference is not None
            and preference.max_wave_count is not None
            and len(player_assignments) >= preference.max_wave_count
        ):
            code = "UNASSIGNED_PLAYER_CONFLICT"
            params = {"maxWaveCount": preference.max_wave_count}
        elif all(
            any(assignment.wave_no == wave_no for assignment in player_assignments)
            for wave_no in allowed
        ):
            code = "UNASSIGNED_PLAYER_CONFLICT"
            params = {"blockedWaves": list(allowed)}
        elif len(assignments) >= capacity:
            code = "UNASSIGNED_CAPACITY"
            params = {"capacity": capacity}
        else:
            code = "UNASSIGNED_ROLE_COMPOSITION"
            params = {"roleType": participant.role_type.value}
        reasons.append(UnassignedReason(participant_id, code, params))
    return tuple(reasons)


def _objective_summary(
    solver_input: SolverInput,
    summaries: tuple[TeamSummary, ...],
    special_assignments: list[SpecialAssignment],
) -> ObjectiveSummary:
    team_by_key = {team.team_key: team for team in solver_input.dungeon.teams}
    by_wave: dict[int, list[TeamSummary]] = defaultdict(list)
    for summary in summaries:
        by_wave[summary.wave_no].append(summary)
    complete_teams = [
        summary
        for summary in summaries
        if summary.member_count == team_by_key[summary.team_key].member_count
        and summary.composition_code is not None
    ]
    complete_waves = [
        wave_no
        for wave_no, wave_summaries in by_wave.items()
        if len(wave_summaries) == len(solver_input.dungeon.teams)
        and all(summary in complete_teams for summary in wave_summaries)
    ]
    preferred_codes = {
        team.team_key: min(
            (
                rule
                for rule in solver_input.dungeon.composition_rules.allowed
                if team.team_key in rule.applicable_team_keys
            ),
            key=lambda rule: rule.priority,
        ).code
        for team in solver_input.dungeon.teams
    }
    damage_totals = [
        sum(summary.damage_total for summary in by_wave[wave_no]) for wave_no in complete_waves
    ]
    buffer_totals = [
        sum(summary.buffer_total for summary in by_wave[wave_no]) for wave_no in complete_waves
    ]
    violations = _strength_order_violations(solver_input, by_wave, set(complete_waves))
    return ObjectiveSummary(
        assigned_count=sum(summary.member_count for summary in summaries),
        participant_count=len(solver_input.participants),
        complete_wave_count=len(complete_waves),
        complete_team_count=len(complete_teams),
        preferred_composition_count=sum(
            summary.composition_code == preferred_codes[summary.team_key]
            for summary in complete_teams
        ),
        special_rule_satisfied_count=len(special_assignments),
        damage_spread=max(damage_totals) - min(damage_totals) if damage_totals else 0,
        buffer_spread=max(buffer_totals) - min(buffer_totals) if buffer_totals else 0,
        strength_order_violation_count=len(violations),
    )


def _strength_order_violations(
    solver_input: SolverInput,
    by_wave: dict[int, list[TeamSummary]],
    complete_waves: set[int],
) -> list[tuple[int, RoleType, str, str, int, int]]:
    violations: list[tuple[int, RoleType, str, str, int, int]] = []
    for wave_no in sorted(complete_waves):
        summary_by_team = {summary.team_key: summary for summary in by_wave[wave_no]}
        for order in solver_input.dungeon.strength_order_rules.orders:
            for stronger_key, weaker_key in zip(order.teams, order.teams[1:], strict=False):
                stronger_summary = summary_by_team[stronger_key]
                weaker_summary = summary_by_team[weaker_key]
                stronger = (
                    stronger_summary.damage_total
                    if order.metric == RoleType.DAMAGE
                    else stronger_summary.buffer_total
                )
                weaker = (
                    weaker_summary.damage_total
                    if order.metric == RoleType.DAMAGE
                    else weaker_summary.buffer_total
                )
                if stronger < weaker:
                    violations.append(
                        (wave_no, order.metric, stronger_key, weaker_key, stronger, weaker)
                    )
    return violations


def _solver_issues(
    solver_input: SolverInput,
    summaries: tuple[TeamSummary, ...],
    special_assignments: list[SpecialAssignment],
) -> tuple[SolverIssue, ...]:
    team_by_key = {team.team_key: team for team in solver_input.dungeon.teams}
    by_wave: dict[int, list[TeamSummary]] = defaultdict(list)
    for summary in summaries:
        by_wave[summary.wave_no].append(summary)
    complete_waves = {
        wave_no
        for wave_no, wave_summaries in by_wave.items()
        if len(wave_summaries) == len(team_by_key)
        and all(
            summary.member_count == team_by_key[summary.team_key].member_count
            and summary.composition_code is not None
            for summary in wave_summaries
        )
    }
    issues: list[SolverIssue] = []
    special_counts: defaultdict[tuple[int, str], int] = defaultdict(int)
    for assignment in special_assignments:
        special_counts[assignment.wave_no, assignment.rule_code] += 1
    for rule in solver_input.dungeon.special_role_rules.rules:
        for wave_no in sorted(complete_waves):
            actual = special_counts[wave_no, rule.code]
            if rule.required_for_complete_wave and actual < rule.count_per_wave:
                issues.append(
                    SolverIssue(
                        "WARNING",
                        "MISSING_WAVE_CORE",
                        {
                            "waveNo": wave_no,
                            "ruleCode": rule.code,
                            "required": rule.count_per_wave,
                            "current": actual,
                        },
                    )
                )
    for (
        wave_no,
        metric,
        stronger,
        weaker,
        stronger_value,
        weaker_value,
    ) in _strength_order_violations(solver_input, by_wave, complete_waves):
        issues.append(
            SolverIssue(
                "WARNING",
                f"{metric.value}_ORDER_VIOLATION",
                {
                    "waveNo": wave_no,
                    "strongerTeamKey": stronger,
                    "weakerTeamKey": weaker,
                    "strongerValue": stronger_value,
                    "weakerValue": weaker_value,
                },
            )
        )
    return tuple(issues)
