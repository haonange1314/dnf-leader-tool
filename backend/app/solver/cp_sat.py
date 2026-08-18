from collections import defaultdict

from ortools.sat.python import cp_model

from app.schemas.dungeon import RoleType
from app.solver.models import (
    SolverAssignment,
    SolverInput,
    SolverResult,
    SolverStatus,
    SpecialAssignment,
    TeamSummary,
)


def solve(solver_input: SolverInput) -> SolverResult:
    _validate_input(solver_input)
    model = cp_model.CpModel()
    participants = solver_input.participants
    teams = solver_input.dungeon.teams
    waves = range(1, solver_input.wave_count + 1)

    x: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for participant_index, participant in enumerate(participants):
        allowed = set(participant.allowed_waves or waves)
        for wave_no in waves:
            for team_index, _team in enumerate(teams):
                variable = model.new_bool_var(f"x_{participant_index}_{wave_no}_{team_index}")
                x[participant_index, wave_no, team_index] = variable
                if wave_no not in allowed:
                    model.add(variable == 0)

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
    for indices in participant_indices_by_player.values():
        for wave_no in waves:
            model.add(
                sum(
                    x[participant_index, wave_no, team_index]
                    for participant_index in indices
                    for team_index, _team in enumerate(teams)
                )
                <= 1
            )

    team_full: dict[tuple[int, int], cp_model.IntVar] = {}
    selected_composition: dict[tuple[int, int, int], cp_model.IntVar] = {}
    composition_rules = solver_input.dungeon.composition_rules.allowed
    for wave_no in waves:
        for team_index, team in enumerate(teams):
            member_count = sum(
                x[participant_index, wave_no, team_index]
                for participant_index, _participant in enumerate(participants)
            )
            model.add(member_count <= team.member_count)
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
    team_index_by_key = {team.team_key: index for index, team in enumerate(teams)}
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

    max_score = max((participant.score for participant in participants), default=0)
    objective_terms: list[cp_model.LinearExpr] = []
    objective_terms.append(1_000_000 * cp_model.LinearExpr.sum(assigned))
    objective_terms.append(100_000 * cp_model.LinearExpr.sum(special_satisfied))
    objective_terms.append(10_000 * cp_model.LinearExpr.sum(list(team_full.values())))

    max_priority = max((rule.priority for rule in composition_rules), default=1)
    for (wave_no, team_index, rule_index), variable in selected_composition.items():
        del wave_no, team_index
        priority = composition_rules[rule_index].priority
        objective_terms.append((max_priority - priority + 1) * 1_000 * variable)

    for participant_index, _participant in enumerate(participants):
        for wave_no in waves:
            early_weight = solver_input.wave_count - wave_no + 1
            team_assignments = [
                x[participant_index, wave_no, team_index] for team_index, _team in enumerate(teams)
            ]
            objective_terms.append(early_weight * cp_model.LinearExpr.sum(team_assignments))

    metric_totals: dict[tuple[RoleType, int, int], cp_model.IntVar] = {}
    score_upper_bound = max_score * len(participants)
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

    for order in solver_input.dungeon.strength_order_rules.orders:
        for wave_no in waves:
            for stronger_key, weaker_key in zip(order.teams, order.teams[1:], strict=False):
                stronger = metric_totals[order.metric, wave_no, team_index_by_key[stronger_key]]
                weaker = metric_totals[order.metric, wave_no, team_index_by_key[weaker_key]]
                slack = model.new_int_var(0, score_upper_bound, "strength_order_slack")
                model.add(slack >= weaker - stronger)
                objective_terms.append(-slack)

    for metric in solver_input.dungeon.optimization_rules.balance_across_waves:
        wave_totals: list[cp_model.LinearExpr] = []
        for wave_no in waves:
            wave_totals.append(
                cp_model.LinearExpr.sum(
                    [
                        metric_totals[metric, wave_no, team_index]
                        for team_index, _team in enumerate(teams)
                    ]
                )
            )
        maximum = model.new_int_var(0, score_upper_bound, f"{metric.value}_wave_max")
        minimum = model.new_int_var(0, score_upper_bound, f"{metric.value}_wave_min")
        model.add_max_equality(maximum, wave_totals)
        model.add_min_equality(minimum, wave_totals)
        objective_terms.append(-(maximum - minimum))

    assigned_total = cp_model.LinearExpr.sum(assigned)
    model.maximize(assigned_total)
    availability_solver = cp_model.CpSolver()
    availability_solver.parameters.max_time_in_seconds = max(
        0.05, solver_input.time_limit_seconds * 0.3
    )
    availability_solver.parameters.random_seed = solver_input.random_seed
    availability_solver.parameters.num_search_workers = 1
    availability_status = availability_solver.solve(model)
    if _status(availability_status) not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return SolverResult(
            status=_status(availability_status),
            assignments=(),
            special_assignments=(),
            unassigned_participant_ids=tuple(p.participant_id for p in participants),
            team_summaries=(),
            objective_value=None,
            wall_time_seconds=availability_solver.wall_time,
        )

    best_assigned_count = round(availability_solver.value(assigned_total))
    model.add(assigned_total == best_assigned_count)
    for variable in x.values():
        model.add_hint(variable, availability_solver.value(variable))

    special_solver_wall_time = 0.0
    if special_satisfied:
        special_total = cp_model.LinearExpr.sum(special_satisfied)
        model.maximize(special_total)
        special_solver = cp_model.CpSolver()
        special_solver.parameters.max_time_in_seconds = max(
            0.05,
            min(
                2.0,
                (solver_input.time_limit_seconds - availability_solver.wall_time) * 0.3,
            ),
        )
        special_solver.parameters.random_seed = solver_input.random_seed
        special_solver.parameters.num_search_workers = 1
        special_status = special_solver.solve(model)
        if _status(special_status) in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
            best_special_count = round(special_solver.value(special_total))
            model.add(special_total == best_special_count)
            model.clear_hints()  # type: ignore[no-untyped-call]
            for variable in x.values():
                model.add_hint(variable, special_solver.value(variable))
            for variable in special_variables.values():
                model.add_hint(variable, special_solver.value(variable))
        special_solver_wall_time = special_solver.wall_time

    model.maximize(cp_model.LinearExpr.sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(
        0.05,
        solver_input.time_limit_seconds
        - availability_solver.wall_time
        - special_solver_wall_time,
    )
    solver.parameters.random_seed = solver_input.random_seed
    solver.parameters.num_search_workers = 1
    status_code = solver.solve(model)
    status = _status(status_code)
    if status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return SolverResult(
            status=status,
            assignments=(),
            special_assignments=(),
            unassigned_participant_ids=tuple(p.participant_id for p in participants),
            team_summaries=(),
            objective_value=None,
            wall_time_seconds=(
                availability_solver.wall_time + special_solver_wall_time + solver.wall_time
            ),
        )

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
    return SolverResult(
        status=status,
        assignments=tuple(assignments),
        special_assignments=tuple(special_assignments),
        unassigned_participant_ids=unassigned,
        team_summaries=summaries,
        objective_value=solver.objective_value,
        wall_time_seconds=(
            availability_solver.wall_time + special_solver_wall_time + solver.wall_time
        ),
    )


def _validate_input(solver_input: SolverInput) -> None:
    if not 1 <= solver_input.wave_count <= 50:
        raise ValueError("wave_count 必须位于 1..50")
    if len({participant.participant_id for participant in solver_input.participants}) != len(
        solver_input.participants
    ):
        raise ValueError("participant_id 必须唯一")
    if any(participant.score < 0 for participant in solver_input.participants):
        raise ValueError("score 不能为负数")


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
