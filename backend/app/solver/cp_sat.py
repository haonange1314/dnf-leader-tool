from collections import defaultdict
from math import lcm

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
    SolverScheduleRuleType,
    SolverStatus,
    SpecialAssignment,
    TeamSummary,
    UnassignedReason,
)

INT64_MAX = (1 << 63) - 1
_AGGREGATE_HINT_SUPPORTED_RULE_TYPES = frozenset(
    {
        SolverScheduleRuleType.PLAYER_ALLOWED_WAVES,
        SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES,
        SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE,
        SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE,
        SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM,
        SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE,
        SolverScheduleRuleType.PLAYER_PREFER_CONTIGUOUS,
        SolverScheduleRuleType.CHARACTER_PREFER_TEAM,
    }
)


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

    for schedule_rule in solver_input.schedule_rules:
        if schedule_rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES:
            rule_allowed_waves = set(schedule_rule.waves)
            for participant_index, participant in enumerate(participants):
                if participant.player_id not in schedule_rule.player_ids:
                    continue
                for wave_no in waves:
                    if wave_no not in rule_allowed_waves:
                        for team_index, _team in enumerate(teams):
                            model.add(x[participant_index, wave_no, team_index] == 0)
        elif schedule_rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES:
            for participant_index, participant in enumerate(participants):
                if participant.player_id not in schedule_rule.player_ids:
                    continue
                for wave_no in schedule_rule.waves:
                    for team_index, _team in enumerate(teams):
                        model.add(x[participant_index, wave_no, team_index] == 0)
        elif schedule_rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
            player_ids = set(schedule_rule.player_ids)
            for wave_no in waves:
                model.add(
                    sum(
                        x[participant_index, wave_no, team_index]
                        for participant_index, participant in enumerate(participants)
                        if participant.player_id in player_ids
                        for team_index, _team in enumerate(teams)
                    )
                    <= 1
                )
        elif schedule_rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE:
            participant_index = participant_index_by_id[schedule_rule.participant_id or ""]
            model.add(
                sum(
                    x[participant_index, schedule_rule.waves[0], team_index]
                    for team_index, _team in enumerate(teams)
                )
                == 1
            )
        elif schedule_rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM:
            participant_index = participant_index_by_id[schedule_rule.participant_id or ""]
            target_team_index = team_index_by_key[schedule_rule.team_key or ""]
            model.add(
                sum(
                    x[participant_index, wave_no, target_team_index]
                    for wave_no in waves
                )
                == 1
            )

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

    player_wave_usage: dict[tuple[str, int], cp_model.IntVar] = {}

    def player_wave_variables(player_id: str) -> dict[int, cp_model.IntVar]:
        indices = participant_indices_by_player[player_id]
        result: dict[int, cp_model.IntVar] = {}
        for wave_no in waves:
            key = (player_id, wave_no)
            used = player_wave_usage.get(key)
            if used is None:
                used = model.new_bool_var(f"player_wave_{player_id}_{wave_no}")
                model.add(
                    used
                    == sum(
                        x[participant_index, wave_no, team_index]
                        for participant_index in indices
                        for team_index, _team in enumerate(teams)
                    )
                )
                player_wave_usage[key] = used
            result[wave_no] = used
        return result

    def contiguous_penalty(
        player_id: str,
        player_wave: dict[int, cp_model.IntVar],
        suffix: str,
    ) -> cp_model.IntVar:
        assigned_count = cp_model.LinearExpr.sum(list(player_wave.values()))
        any_used = model.new_bool_var(f"player_any_{player_id}_{suffix}")
        model.add_max_equality(any_used, list(player_wave.values()))
        latest = model.new_int_var(
            0, solver_input.wave_count, f"player_latest_{player_id}_{suffix}"
        )
        model.add_max_equality(latest, [wave_no * used for wave_no, used in player_wave.items()])
        earliest_candidates: list[cp_model.IntVar] = []
        for wave_no, used in player_wave.items():
            candidate = model.new_int_var(
                1,
                solver_input.wave_count * 2 + 1,
                f"player_earliest_candidate_{player_id}_{wave_no}_{suffix}",
            )
            model.add(candidate == wave_no + (solver_input.wave_count + 1) * (1 - used))
            earliest_candidates.append(candidate)
        earliest = model.new_int_var(
            1,
            solver_input.wave_count * 2 + 1,
            f"player_earliest_{player_id}_{suffix}",
        )
        model.add_min_equality(earliest, earliest_candidates)
        gap = model.new_int_var(
            0, solver_input.wave_count, f"player_gap_{player_id}_{suffix}"
        )
        model.add(gap == latest - earliest + 1 - assigned_count).only_enforce_if(any_used)
        model.add(gap == 0).only_enforce_if(~any_used)
        return gap

    preference_penalties: list[cp_model.LinearExpr] = []
    for player_id, _indices in participant_indices_by_player.items():
        preference = preference_by_player.get(player_id)
        if preference is None:
            continue
        player_wave = player_wave_variables(player_id)
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
            preference_penalties.append(contiguous_penalty(player_id, player_wave, "profile"))

    schedule_rule_penalties: list[cp_model.LinearExpr] = []
    for schedule_rule in solver_input.schedule_rules:
        if schedule_rule.type == SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE:
            preferred_waves = set(schedule_rule.waves)
            for player_id in schedule_rule.player_ids:
                player_wave = player_wave_variables(player_id)
                schedule_rule_penalties.append(
                    cp_model.LinearExpr.sum(
                        [
                            used
                            for wave_no, used in player_wave.items()
                            if wave_no not in preferred_waves
                        ]
                    )
                )
        elif schedule_rule.type == SolverScheduleRuleType.PLAYER_PREFER_CONTIGUOUS:
            for player_id in schedule_rule.player_ids:
                player_wave = player_wave_variables(player_id)
                schedule_rule_penalties.append(
                    contiguous_penalty(
                        player_id, player_wave, f"rule_{schedule_rule.rule_id}"
                    )
                )
        elif schedule_rule.type == SolverScheduleRuleType.CHARACTER_PREFER_TEAM:
            participant_index = participant_index_by_id[
                schedule_rule.participant_id or ""
            ]
            target_team_index = team_index_by_key[schedule_rule.team_key or ""]
            schedule_rule_penalties.append(
                assigned[participant_index]
                - sum(
                    x[participant_index, wave_no, target_team_index]
                    for wave_no in waves
                )
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

    buffer_count_targets = _buffer_count_targets(solver_input)
    for (wave_no, team_key), target_count in buffer_count_targets.items():
        team_index = team_index_by_key[team_key]
        model.add(
            sum(
                x[participant_index, wave_no, team_index]
                for participant_index, participant in enumerate(participants)
                if participant.role_type == RoleType.BUFFER
            )
            == target_count
        )

    damage_rule = (
        solver_input.dungeon.optimization_rules.damage_placement
        if buffer_count_targets
        else None
    )
    if damage_rule is not None:
        primary_team_index = team_index_by_key[damage_rule.primary_team_key]
        primary_capacity = teams[primary_team_index].member_count
        for wave_no in waves:
            model.add(
                sum(
                    x[participant_index, wave_no, primary_team_index]
                    for participant_index, participant in enumerate(participants)
                    if participant.role_type == RoleType.DAMAGE
                )
                == primary_capacity
                - buffer_count_targets[wave_no, damage_rule.primary_team_key]
            )

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
    buffer_placement_targets = _build_buffer_placement_targets(
        solver_input, team_index_by_key
    )
    buffer_placement_terms = [
        x[participant_index, wave_no, team_index]
        for participant_index, wave_no, team_index in buffer_placement_targets
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
    buffer_strength_order_penalties: list[cp_model.LinearExpr] = []
    hard_buffer_strength_order = (
        solver_input.dungeon.optimization_rules.buffer_placement is not None
        and any(
            order.metric == RoleType.BUFFER
            for order in solver_input.dungeon.strength_order_rules.orders
        )
    )
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
                if (
                    order.metric == RoleType.BUFFER
                    and solver_input.dungeon.optimization_rules.buffer_placement is not None
                ):
                    # A configured buffer-placement phase means buffers are fixed
                    # before damage dealers are assigned. Every wave must
                    # preserve the configured buffer strength order; otherwise a
                    # time-limited soft violation would be frozen permanently.
                    model.add(stronger >= weaker)
                    model.add(slack == 0)
                else:
                    model.add(slack >= weaker - stronger).only_enforce_if(
                        wave_full[wave_no]
                    )
                    model.add(slack == 0).only_enforce_if(~wave_full[wave_no])
                strength_order_penalties.append(slack)
                if order.metric == RoleType.BUFFER:
                    buffer_strength_order_penalties.append(slack)
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

    damage_primary_terms: list[cp_model.LinearExpr] = []
    damage_primary_score: cp_model.LinearExpr | None = None
    damage_pair_wave_terms: list[cp_model.IntVar] = []
    damage_primary_balance_spread: cp_model.IntVar | None = None
    damage_balance_tolerance_excess: cp_model.IntVar | None = None
    damage_balance_spread: cp_model.IntVar | None = None
    damage_average_scale = _damage_average_scale(solver_input)
    if damage_rule is not None:
        primary_team_index = team_index_by_key[damage_rule.primary_team_key]
        primary_slot_count = sum(
            teams[primary_team_index].member_count
            - buffer_count_targets[wave_no, damage_rule.primary_team_key]
            for wave_no in waves
        )
        ranked_damage_indices = sorted(
            (
                participant_index
                for participant_index, participant in enumerate(participants)
                if participant.role_type == RoleType.DAMAGE
            ),
            key=lambda participant_index: (
                -participants[participant_index].score,
                participants[participant_index].participant_id,
            ),
        )
        selected_damage_indices = ranked_damage_indices[:primary_slot_count]
        damage_primary_terms = [
            x[participant_index, wave_no, primary_team_index]
            for participant_index in selected_damage_indices
            for wave_no in waves
        ]
        damage_primary_score = cp_model.LinearExpr.sum(
            [
                participants[participant_index].score
                * x[participant_index, wave_no, primary_team_index]
                for participant_index in ranked_damage_indices
                for wave_no in waves
            ]
        )

        if damage_rule.pair_extremes_in_double_buffer_teams:
            remaining_ranked = list(selected_damage_indices)
            minimum_primary_buffer_count = _buffer_count_bounds(solver_input)[
                damage_rule.primary_team_key
            ][0]
            double_buffer_waves = [
                wave_no
                for wave_no in waves
                if buffer_count_targets[wave_no, damage_rule.primary_team_key]
                > minimum_primary_buffer_count
            ]
            for wave_no in double_buffer_waves:
                if len(remaining_ranked) < 2:
                    break
                strongest_index = remaining_ranked.pop(0)
                weakest_index = remaining_ranked.pop()
                damage_pair_wave_terms.extend(
                    (
                        x[strongest_index, wave_no, primary_team_index],
                        x[weakest_index, wave_no, primary_team_index],
                    )
                )

        primary_single_waves = [
            wave_no
            for wave_no in waves
            if buffer_count_targets[wave_no, damage_rule.primary_team_key]
            == _buffer_count_bounds(solver_input)[damage_rule.primary_team_key][0]
        ]
        if len(primary_single_waves) > 1:
            primary_totals = [
                metric_totals[RoleType.DAMAGE, wave_no, primary_team_index]
                for wave_no in primary_single_waves
            ]
            primary_maximum = model.new_int_var(
                0, score_upper_bound, "damage_primary_single_max"
            )
            primary_minimum = model.new_int_var(
                0, score_upper_bound, "damage_primary_single_min"
            )
            damage_primary_balance_spread = model.new_int_var(
                0, score_upper_bound, "damage_primary_single_spread"
            )
            model.add_max_equality(primary_maximum, primary_totals)
            model.add_min_equality(primary_minimum, primary_totals)
            model.add(
                damage_primary_balance_spread == primary_maximum - primary_minimum
            )

        balanced_full = [
            team_full[wave_no, team_index_by_key[team_key]]
            for wave_no in waves
            for team_key in damage_rule.balanced_team_keys
        ]
        any_balanced_full = model.new_bool_var("damage_balance_any_full")
        model.add_max_equality(any_balanced_full, balanced_full)
        average_upper_bound = score_upper_bound * damage_average_scale
        balanced_averages: list[cp_model.IntVar] = []
        balanced_min_candidates: list[cp_model.IntVar] = []
        for wave_no in waves:
            for team_key in damage_rule.balanced_team_keys:
                team_index = team_index_by_key[team_key]
                full = team_full[wave_no, team_index]
                average = model.new_int_var(
                    0,
                    average_upper_bound,
                    f"damage_average_{wave_no}_{team_index}",
                )
                for rule_index, composition in enumerate(composition_rules):
                    composition_selection = selected_composition.get(
                        (wave_no, team_index, rule_index)
                    )
                    if composition_selection is None:
                        continue
                    damage_count = composition.roles.get(RoleType.DAMAGE, 0)
                    if damage_count:
                        model.add(
                            average * damage_count
                            == metric_totals[RoleType.DAMAGE, wave_no, team_index]
                            * damage_average_scale
                        ).only_enforce_if(composition_selection)
                    else:
                        model.add(average == 0).only_enforce_if(
                            composition_selection
                        )
                model.add(average == 0).only_enforce_if(~full)
                minimum_candidate = model.new_int_var(
                    0,
                    average_upper_bound,
                    f"damage_average_min_candidate_{wave_no}_{team_index}",
                )
                model.add(minimum_candidate == average).only_enforce_if(full)
                model.add(minimum_candidate == average_upper_bound).only_enforce_if(~full)
                balanced_averages.append(average)
                balanced_min_candidates.append(minimum_candidate)

        balance_maximum = model.new_int_var(
            0, average_upper_bound, "damage_balance_average_max"
        )
        balance_minimum = model.new_int_var(
            0, average_upper_bound, "damage_balance_average_min"
        )
        damage_balance_spread = model.new_int_var(
            0, average_upper_bound, "damage_balance_average_spread"
        )
        model.add_max_equality(balance_maximum, balanced_averages)
        model.add_min_equality(balance_minimum, balanced_min_candidates)
        model.add(
            damage_balance_spread == balance_maximum - balance_minimum
        ).only_enforce_if(any_balanced_full)
        model.add(damage_balance_spread == 0).only_enforce_if(~any_balanced_full)
        damage_balance_tolerance_excess = model.new_int_var(
            0, average_upper_bound * 100, "damage_balance_tolerance_excess"
        )
        model.add(
            damage_balance_tolerance_excess
            >= 100 * balance_maximum
            - (100 + solver_input.damage_balance_tolerance_percent) * balance_minimum
        ).only_enforce_if(any_balanced_full)
        model.add(damage_balance_tolerance_excess == 0).only_enforce_if(
            ~any_balanced_full
        )

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
    availability_elapsed = 0.0
    availability_model = model
    availability_objective = assigned_total
    protect_stage_incumbent = False
    target_hint_attempted = False
    has_multi_character_player = any(
        len(indices) > 1 for indices in participant_indices_by_player.values()
    )
    aggregate_hint_supports_rules = all(
        rule.type in _AGGREGATE_HINT_SUPPORTED_RULE_TYPES
        for rule in solver_input.schedule_rules
    )
    if (
        assignment_upper_bound < len(participants) or has_multi_character_player
    ) and aggregate_hint_supports_rules:
        target_hint_attempted = True
        target_hint, target_hint_elapsed, target_hint_count = _find_assignment_target_hint(
            solver_input,
            assignment_upper_bound,
            time_limit_seconds=availability_budget * 0.75,
        )
        availability_elapsed += target_hint_elapsed
        if target_hint is not None and hard_buffer_strength_order:
            (
                target_hint,
                buffer_hint_status,
                buffer_hint_elapsed,
            ) = _repair_buffer_strength_order_hint(solver_input, target_hint)
            availability_elapsed += buffer_hint_elapsed
            if target_hint is None:
                return SolverResult(
                    status=buffer_hint_status,
                    assignments=(),
                    special_assignments=(),
                    unassigned_participant_ids=tuple(
                        participant.participant_id for participant in participants
                    ),
                    unassigned=tuple(
                        UnassignedReason(
                            participant_id=participant.participant_id,
                            code="UNASSIGNED_ROLE_COMPOSITION",
                            message_params={},
                        )
                        for participant in participants
                    ),
                    team_summaries=(),
                    issues=(),
                    objective_summary=ObjectiveSummary(
                        0, len(participants), 0, 0, 0, 0, 0, 0, 0
                    ),
                    objective_value=None,
                    wall_time_seconds=availability_elapsed,
                )
        if target_hint is not None:
            protect_stage_incumbent = True
            model.add(assigned_total >= target_hint_count)
            for key, variable in x.items():
                model.add_hint(variable, target_hint[key])
            remaining_special_by_rule_wave = {
                (rule_index, wave_no): (
                    special_rule.count_per_wave
                    if sum(
                        target_hint[participant_index, wave_no, team_index]
                        for participant_index, _participant in enumerate(participants)
                        for team_index, _team in enumerate(teams)
                    )
                    == solver_input.dungeon.participants_per_wave
                    else 0
                )
                for rule_index, special_rule in enumerate(
                    solver_input.dungeon.special_role_rules.rules
                )
                for wave_no in waves
            }
            special_hint: dict[tuple[int, int, int], int] = {}
            for (rule_index, participant_index, wave_no), variable in special_variables.items():
                special_rule = solver_input.dungeon.special_role_rules.rules[rule_index]
                target_team_index = team_index_by_key[special_rule.target_team_key]
                remaining_key = (rule_index, wave_no)
                selected = int(
                    bool(target_hint[participant_index, wave_no, target_team_index])
                    and remaining_special_by_rule_wave[remaining_key] > 0
                )
                model.add_hint(variable, selected)
                special_hint[rule_index, participant_index, wave_no] = selected
                remaining_special_by_rule_wave[remaining_key] -= selected
            if target_hint_count == assignment_upper_bound:
                model.add(assigned_total == assignment_upper_bound)
                availability_model = model.clone()
                for key, variable in x.items():
                    cloned_variable = availability_model.get_bool_var_from_proto_index(
                        variable.index
                    )
                    # The repaired buffer plan is the first, mandatory phase.
                    # Damage assignments from the aggregate hint may now collide
                    # with a buffer from the same player/wave, so let the full
                    # model place damage dealers around the fixed buffer plan.
                    if (
                        not hard_buffer_strength_order
                        or participants[key[0]].role_type == RoleType.BUFFER
                    ):
                        availability_model.add(cloned_variable == target_hint[key])
                for key, variable in special_variables.items():
                    cloned_variable = availability_model.get_bool_var_from_proto_index(
                        variable.index
                    )
                    if not hard_buffer_strength_order:
                        availability_model.add(cloned_variable == special_hint[key])
                availability_objective = cp_model.LinearExpr.sum(
                    [
                        availability_model.get_bool_var_from_proto_index(variable.index)
                        for variable in assigned
                    ]
                )
    availability_solver, availability_status = _solve_stage(
        availability_model,
        availability_objective,
        maximize=True,
        time_limit_seconds=(
            # A reachable aggregate target can be verified cheaply in the fixed
            # clone. Otherwise the full model keeps its complete availability
            # budget and treats the aggregate result only as a lower-bound hint.
            availability_budget
            if target_hint_attempted
            and (not protect_stage_incumbent or availability_model is model)
            else max(0.05, availability_budget - availability_elapsed)
        ),
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
            wall_time_seconds=availability_elapsed,
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
        incumbent_stage_value = round(best_solver.value(evaluated_objective))
        if protect_stage_incumbent:
            # The reduced-model assignment is already feasible in the full model.
            # Protect only the formal stage objective; search-only tie-breaks must
            # not leak into later lexicographic stages.
            if maximize:
                model.add(evaluated_objective >= incumbent_stage_value)
            else:
                model.add(evaluated_objective <= incumbent_stage_value)
        stage_solver, stage_status = _solve_stage(
            model,
            objective,
            maximize=maximize,
            time_limit_seconds=_stage_budget(solver_input.time_limit_seconds, budget_ratio),
            random_seed=solver_input.random_seed,
        )
        elapsed += stage_solver.wall_time
        if stage_status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
            stage_value = round(stage_solver.value(evaluated_objective))
            stage_improved = (
                stage_value > incumbent_stage_value
                if maximize
                else stage_value < incumbent_stage_value
            )
            if stage_improved or not protect_stage_incumbent:
                best_solver = stage_solver
                _replace_hints(model, hint_variables, stage_solver)
            else:
                stage_value = incumbent_stage_value
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

    if buffer_placement_terms:
        if buffer_strength_order_penalties:
            optimize_and_fix_stage(
                "BUFFER_STRENGTH_ORDER",
                cp_model.LinearExpr.sum(buffer_strength_order_penalties),
                maximize=False,
                budget_ratio=0.06,
                target_value=0,
            )
        optimize_and_fix_stage(
            "BUFFER_PLACEMENT",
            cp_model.LinearExpr.sum(buffer_placement_terms),
            maximize=True,
            budget_ratio=0.10,
            target_value=len(buffer_placement_terms),
        )
        for participant_index, participant in enumerate(participants):
            if participant.role_type != RoleType.BUFFER:
                continue
            for wave_no in waves:
                for team_index, _team in enumerate(teams):
                    variable = x[participant_index, wave_no, team_index]
                    model.add(variable == best_solver.value(variable))

    if damage_primary_terms:
        optimize_and_fix_stage(
            "DAMAGE_PRIMARY_COUNT",
            cp_model.LinearExpr.sum(damage_primary_terms),
            maximize=True,
            budget_ratio=0.08,
            target_value=min(
                len(
                    [
                        participant
                        for participant in participants
                        if participant.role_type == RoleType.DAMAGE
                    ]
                ),
                sum(
                    teams[team_index_by_key[damage_rule.primary_team_key]].member_count
                    - buffer_count_targets[wave_no, damage_rule.primary_team_key]
                    for wave_no in waves
                )
                if damage_rule is not None
                else 0,
            ),
        )
    if damage_primary_score is not None:
        primary_slot_count = (
            sum(
                teams[team_index_by_key[damage_rule.primary_team_key]].member_count
                - buffer_count_targets[wave_no, damage_rule.primary_team_key]
                for wave_no in waves
            )
            if damage_rule is not None
            else 0
        )
        damage_scores = sorted(
            (
                participant.score
                for participant in participants
                if participant.role_type == RoleType.DAMAGE
            ),
            reverse=True,
        )
        optimize_and_fix_stage(
            "DAMAGE_PRIMARY_SCORE",
            damage_primary_score,
            maximize=True,
            budget_ratio=0.08,
            target_value=sum(damage_scores[:primary_slot_count]),
        )
    if damage_pair_wave_terms:
        optimize_and_fix_stage(
            "DAMAGE_PRIMARY_PAIRING",
            cp_model.LinearExpr.sum(damage_pair_wave_terms),
            maximize=True,
            budget_ratio=0.06,
            target_value=len(damage_pair_wave_terms),
        )
    if damage_primary_balance_spread is not None:
        optimize_and_fix_stage(
            "DAMAGE_PRIMARY_BALANCE",
            damage_primary_balance_spread,
            maximize=False,
            budget_ratio=0.06,
            target_value=0,
        )
    if damage_rule is not None:
        primary_team_index = team_index_by_key[damage_rule.primary_team_key]
        for participant_index, participant in enumerate(participants):
            if participant.role_type != RoleType.DAMAGE:
                continue
            for wave_no in waves:
                variable = x[participant_index, wave_no, primary_team_index]
                model.add(variable == best_solver.value(variable))

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

    if damage_balance_tolerance_excess is not None:
        optimize_and_fix_stage(
            "DAMAGE_BALANCE_TOLERANCE",
            damage_balance_tolerance_excess,
            maximize=False,
            budget_ratio=0.06,
            target_value=0,
        )
    if damage_balance_spread is not None:
        optimize_and_fix_stage(
            "DAMAGE_BALANCE_SPREAD",
            damage_balance_spread,
            maximize=False,
            budget_ratio=0.06,
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
        ("SCHEDULE_RULES", schedule_rule_penalties, 0.05),
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
    objective_summary = _objective_summary(
        solver_input, assignments, summaries, special_assignments
    )
    issues = _solver_issues(
        solver_input, summaries, special_assignments, objective_summary
    )
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


def _buffer_count_bounds(
    solver_input: SolverInput,
) -> dict[str, tuple[int, int]]:
    bounds: dict[str, tuple[int, int]] = {}
    for team in solver_input.dungeon.teams:
        counts = [
            composition.roles.get(RoleType.BUFFER, 0)
            for composition in solver_input.dungeon.composition_rules.allowed
            if team.team_key in composition.applicable_team_keys
        ]
        bounds[team.team_key] = (min(counts), max(counts))
    return bounds


def _buffer_count_targets(solver_input: SolverInput) -> dict[tuple[int, str], int]:
    """Distribute all buffers by configured team priority, then by wave order."""

    rule = solver_input.dungeon.optimization_rules.buffer_placement
    if rule is None:
        return {}
    bounds = _buffer_count_bounds(solver_input)
    targets = {
        (wave_no, team_key): bounds[team_key][0]
        for team_key in rule.team_order
        for wave_no in range(1, solver_input.wave_count + 1)
    }
    buffer_count = sum(
        participant.role_type == RoleType.BUFFER
        for participant in solver_input.participants
    )
    remaining = buffer_count - sum(targets.values())
    if remaining < 0:
        return {}
    for team_key in rule.double_buffer_team_keys:
        _minimum, maximum = bounds[team_key]
        for wave_no in range(1, solver_input.wave_count + 1):
            while remaining and targets[wave_no, team_key] < maximum:
                targets[wave_no, team_key] += 1
                remaining -= 1
    if remaining:
        return {}
    return targets


def _build_buffer_placement_targets(
    solver_input: SolverInput,
    team_index_by_key: dict[str, int],
) -> tuple[tuple[int, int, int], ...]:
    """Build the ideal high-low buffer assignment without weakening hard rules."""

    rule = solver_input.dungeon.optimization_rules.buffer_placement
    if rule is None:
        return ()
    targets = _buffer_count_targets(solver_input)
    if not targets:
        return ()
    bounds = _buffer_count_bounds(solver_input)
    remaining = [
        participant_index
        for participant_index, participant in sorted(
            enumerate(solver_input.participants),
            key=lambda item: (-item[1].score, item[1].participant_id),
        )
        if participant.role_type == RoleType.BUFFER
    ]
    placements: list[tuple[int, int, int]] = []
    placed_count: defaultdict[tuple[int, str], int] = defaultdict(int)

    def take_largest(wave_no: int, team_key: str) -> None:
        if remaining:
            placements.append(
                (remaining.pop(0), wave_no, team_index_by_key[team_key])
            )
            placed_count[wave_no, team_key] += 1

    def take_smallest(wave_no: int, team_key: str) -> None:
        if remaining:
            placements.append((remaining.pop(), wave_no, team_index_by_key[team_key]))
            placed_count[wave_no, team_key] += 1

    if rule.pair_extremes:
        for team_key in rule.double_buffer_team_keys:
            minimum, _maximum = bounds[team_key]
            for wave_no in range(1, solver_input.wave_count + 1):
                if targets[wave_no, team_key] <= minimum:
                    continue
                take_largest(wave_no, team_key)
                take_smallest(wave_no, team_key)

    for team_key in rule.team_order:
        for wave_no in range(1, solver_input.wave_count + 1):
            while placed_count[wave_no, team_key] < targets[wave_no, team_key]:
                take_largest(wave_no, team_key)
    return tuple(placements)


def _repair_buffer_strength_order_hint(
    solver_input: SolverInput,
    hint: dict[tuple[int, int, int], int],
) -> tuple[
    dict[tuple[int, int, int], int] | None,
    SolverStatus,
    float,
]:
    """Repair the aggregate hint with a small buffer-only assignment model."""

    order_rules = tuple(
        order
        for order in solver_input.dungeon.strength_order_rules.orders
        if order.metric == RoleType.BUFFER
    )
    buffer_targets = _buffer_count_targets(solver_input)
    if not order_rules or not buffer_targets:
        return hint, SolverStatus.FEASIBLE, 0.0

    model = cp_model.CpModel()
    participants = solver_input.participants
    teams = solver_input.dungeon.teams
    waves = tuple(range(1, solver_input.wave_count + 1))
    team_index_by_key = {team.team_key: index for index, team in enumerate(teams)}
    participant_index_by_id = {
        participant.participant_id: index for index, participant in enumerate(participants)
    }
    buffer_indices = tuple(
        participant_index
        for participant_index, participant in enumerate(participants)
        if participant.role_type == RoleType.BUFFER
    )
    allowed_waves_by_player = {
        player_id: set(waves)
        for player_id in {participant.player_id for participant in participants}
    }
    forbidden_waves_by_player: defaultdict[str, set[int]] = defaultdict(set)
    required_waves_by_participant: dict[int, set[int]] = {}
    required_teams_by_participant: dict[int, set[int]] = {}
    for rule in solver_input.schedule_rules:
        if rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES:
            for player_id in rule.player_ids:
                allowed_waves_by_player[player_id].intersection_update(rule.waves)
        elif rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES:
            for player_id in rule.player_ids:
                forbidden_waves_by_player[player_id].update(rule.waves)
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE:
            required_waves_by_participant[
                participant_index_by_id[rule.participant_id or ""]
            ] = set(rule.waves)
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM:
            required_teams_by_participant[
                participant_index_by_id[rule.participant_id or ""]
            ] = {team_index_by_key[rule.team_key or ""]}
    for locked in solver_input.locked_assignments:
        participant_index = participant_index_by_id[locked.participant_id]
        if participants[participant_index].role_type != RoleType.BUFFER:
            continue
        required_waves_by_participant[participant_index] = {locked.wave_no}
        required_teams_by_participant[participant_index] = {
            team_index_by_key[locked.team_key]
        }

    variables: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for participant_index in buffer_indices:
        participant = participants[participant_index]
        participant_waves = set(
            waves if participant.allowed_waves is None else participant.allowed_waves
        )
        participant_waves.intersection_update(
            allowed_waves_by_player[participant.player_id]
        )
        participant_waves.difference_update(
            forbidden_waves_by_player[participant.player_id]
        )
        if participant_index in required_waves_by_participant:
            participant_waves.intersection_update(
                required_waves_by_participant[participant_index]
            )
        participant_teams = {
            team_index
            for team_index, team in enumerate(teams)
            if participant.allowed_team_keys is None
            or team.team_key in participant.allowed_team_keys
        }
        if participant_index in required_teams_by_participant:
            participant_teams.intersection_update(
                required_teams_by_participant[participant_index]
            )
        participant_variables: list[cp_model.IntVar] = []
        for wave_no in waves:
            for team_index, _team in enumerate(teams):
                variable = model.new_bool_var(
                    f"buffer_hint_{participant_index}_{wave_no}_{team_index}"
                )
                variables[participant_index, wave_no, team_index] = variable
                participant_variables.append(variable)
                if (
                    wave_no not in participant_waves
                    or team_index not in participant_teams
                ):
                    model.add(variable == 0)
                model.add_hint(
                    variable, hint[participant_index, wave_no, team_index]
                )
        model.add(sum(participant_variables) == 1)

    buffer_indices_by_player: defaultdict[str, list[int]] = defaultdict(list)
    for participant_index in buffer_indices:
        buffer_indices_by_player[participants[participant_index].player_id].append(
            participant_index
        )
    preference_by_player = {
        preference.player_id: preference
        for preference in solver_input.player_preferences
    }
    for player_id, player_buffer_indices in buffer_indices_by_player.items():
        for wave_no in waves:
            model.add(
                sum(
                    variables[participant_index, wave_no, team_index]
                    for participant_index in player_buffer_indices
                    for team_index, _team in enumerate(teams)
                )
                <= 1
            )
        preference = preference_by_player.get(player_id)
        if preference is not None and preference.max_wave_count is not None:
            model.add(
                sum(
                    variables[participant_index, wave_no, team_index]
                    for participant_index in player_buffer_indices
                    for wave_no in waves
                    for team_index, _team in enumerate(teams)
                )
                <= preference.max_wave_count
            )

    for rule in solver_input.schedule_rules:
        if rule.type != SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
            continue
        player_ids = set(rule.player_ids)
        for wave_no in waves:
            model.add(
                sum(
                    variables[participant_index, wave_no, team_index]
                    for participant_index in buffer_indices
                    if participants[participant_index].player_id in player_ids
                    for team_index, _team in enumerate(teams)
                )
                <= 1
            )

    for (wave_no, team_key), target_count in buffer_targets.items():
        team_index = team_index_by_key[team_key]
        model.add(
            sum(
                variables[participant_index, wave_no, team_index]
                for participant_index in buffer_indices
            )
            == target_count
        )
    for order in order_rules:
        for wave_no in waves:
            totals = {
                team_key: sum(
                    participants[participant_index].score
                    * variables[
                        participant_index, wave_no, team_index_by_key[team_key]
                    ]
                    for participant_index in buffer_indices
                )
                for team_key in order.teams
            }
            for stronger_key, weaker_key in zip(
                order.teams, order.teams[1:], strict=False
            ):
                model.add(totals[stronger_key] >= totals[weaker_key])

    ideal_targets = set(
        _build_buffer_placement_targets(solver_input, team_index_by_key)
    )
    model.maximize(
        sum(
            (100 if hint[key] else 0) * variable
            + (1 if key in ideal_targets else 0) * variable
            for key, variable in variables.items()
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(
        0.5, min(2.0, solver_input.time_limit_seconds * 0.10)
    )
    solver.parameters.random_seed = solver_input.random_seed
    solver.parameters.num_search_workers = 1
    status = _status(solver.solve(model))
    if status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return None, status, solver.wall_time

    repaired = dict(hint)
    for key, variable in variables.items():
        repaired[key] = round(solver.value(variable))
    return repaired, status, solver.wall_time


def _damage_average_scale(solver_input: SolverInput) -> int:
    rule = solver_input.dungeon.optimization_rules.damage_placement
    if rule is None:
        return 1
    relevant_team_keys = {rule.primary_team_key, *rule.balanced_team_keys}
    damage_counts = {
        composition.roles.get(RoleType.DAMAGE, 0)
        for composition in solver_input.dungeon.composition_rules.allowed
        if relevant_team_keys.intersection(composition.applicable_team_keys)
        and composition.roles.get(RoleType.DAMAGE, 0) > 0
    }
    return lcm(*damage_counts) if damage_counts else 1


def _find_assignment_target_hint(
    solver_input: SolverInput,
    assignment_target: int,
    *,
    time_limit_seconds: float,
) -> tuple[dict[tuple[int, int, int], int] | None, float, int]:
    """Find a maximum-cardinality assignment without downstream scoring variables.

    Dense rosters with many characters per player create a large amount of symmetry.
    Solving the complete quality model from scratch can spend most of the availability
    stage proving a cardinality target that only depends on assignment, capacity and
    composition constraints. This reduced model establishes that target and supplies
    a complete assignment hint to the quality model.
    """
    model = cp_model.CpModel()
    participants = solver_input.participants
    teams = solver_input.dungeon.teams
    waves = tuple(range(1, solver_input.wave_count + 1))
    team_index_by_key = {team.team_key: index for index, team in enumerate(teams)}
    participant_index_by_id = {
        participant.participant_id: index for index, participant in enumerate(participants)
    }
    group_key_by_participant: dict[
        int, tuple[str, RoleType, tuple[int, ...] | None, tuple[str, ...] | None]
    ] = {}
    participant_indices_by_group: dict[
        tuple[str, RoleType, tuple[int, ...] | None, tuple[str, ...] | None], list[int]
    ] = defaultdict(list)
    for participant_index, participant in enumerate(participants):
        group_key = (
            participant.player_id,
            participant.role_type,
            participant.allowed_waves,
            participant.allowed_team_keys,
        )
        group_key_by_participant[participant_index] = group_key
        participant_indices_by_group[group_key].append(participant_index)
    group_keys = tuple(participant_indices_by_group)
    group_index_by_key = {group_key: index for index, group_key in enumerate(group_keys)}
    team_rank_by_role = {
        order.metric: {team_key: rank for rank, team_key in enumerate(order.teams)}
        for order in solver_input.dungeon.strength_order_rules.orders
    }
    ordered_damage_rule = (
        solver_input.dungeon.optimization_rules.damage_placement
        if _buffer_count_targets(solver_input)
        else None
    )
    if ordered_damage_rule is not None:
        damage_team_order = (
            ordered_damage_rule.primary_team_key,
            *ordered_damage_rule.balanced_team_keys,
            *(
                team.team_key
                for team in teams
                if team.team_key
                not in {
                    ordered_damage_rule.primary_team_key,
                    *ordered_damage_rule.balanced_team_keys,
                }
            ),
        )
        team_rank_by_role[RoleType.DAMAGE] = {
            team_key: rank for rank, team_key in enumerate(damage_team_order)
        }

    group_assignment: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for group_index, group_key in enumerate(group_keys):
        _player_id, _role_type, allowed_waves, allowed_team_keys = group_key
        allowed_wave_set = set(waves if allowed_waves is None else allowed_waves)
        for wave_no in waves:
            for team_index, team in enumerate(teams):
                variable = model.new_bool_var(
                    f"target_group_{group_index}_{wave_no}_{team_index}"
                )
                group_assignment[group_index, wave_no, team_index] = variable
                if wave_no not in allowed_wave_set or (
                    allowed_team_keys is not None and team.team_key not in allowed_team_keys
                ):
                    model.add(variable == 0)
        model.add(
            sum(
                group_assignment[group_index, wave_no, team_index]
                for wave_no in waves
                for team_index, _team in enumerate(teams)
            )
            <= len(participant_indices_by_group[group_key])
        )

    identity_allowed_locations: dict[int, set[tuple[int, int]]] = {}

    def restrict_identity(
        participant_index: int,
        allowed_locations: set[tuple[int, int]],
    ) -> None:
        participant = participants[participant_index]
        participant_waves = set(
            waves if participant.allowed_waves is None else participant.allowed_waves
        )
        participant_teams = {
            team_index
            for team_index, team in enumerate(teams)
            if participant.allowed_team_keys is None
            or team.team_key in participant.allowed_team_keys
        }
        current = identity_allowed_locations.setdefault(
            participant_index,
            {
                (wave_no, team_index)
                for wave_no in participant_waves
                for team_index in participant_teams
            },
        )
        current.intersection_update(allowed_locations)

    for locked in solver_input.locked_assignments:
        restrict_identity(
            participant_index_by_id[locked.participant_id],
            {(locked.wave_no, team_index_by_key[locked.team_key])},
        )
    for schedule_rule in solver_input.schedule_rules:
        if schedule_rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE:
            restrict_identity(
                participant_index_by_id[schedule_rule.participant_id or ""],
                {
                    (schedule_rule.waves[0], team_index)
                    for team_index, _team in enumerate(teams)
                },
            )
        elif schedule_rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM:
            restrict_identity(
                participant_index_by_id[schedule_rule.participant_id or ""],
                {
                    (wave_no, team_index_by_key[schedule_rule.team_key or ""])
                    for wave_no in waves
                },
            )

    identity_assignment: dict[tuple[int, int, int], cp_model.IntVar] = {}
    identities_by_group_position: dict[
        tuple[int, int, int], list[tuple[int, cp_model.IntVar]]
    ] = defaultdict(list)
    for participant_index, allowed_locations in identity_allowed_locations.items():
        group_index = group_index_by_key[group_key_by_participant[participant_index]]
        variables: list[cp_model.IntVar] = []
        for wave_no, team_index in sorted(allowed_locations):
            variable = model.new_bool_var(
                f"target_identity_{participant_index}_{wave_no}_{team_index}"
            )
            model.add(variable <= group_assignment[group_index, wave_no, team_index])
            identity_assignment[participant_index, wave_no, team_index] = variable
            identities_by_group_position[group_index, wave_no, team_index].append(
                (participant_index, variable)
            )
            variables.append(variable)
        model.add(sum(variables) == 1)
    for (group_index, wave_no, team_index), identities in (
        identities_by_group_position.items()
    ):
        model.add(
            sum(variable for _participant_index, variable in identities)
            <= group_assignment[group_index, wave_no, team_index]
        )

    group_indices_by_player: dict[str, list[int]] = defaultdict(list)
    for group_index, (player_id, _role_type, _waves, _teams) in enumerate(group_keys):
        group_indices_by_player[player_id].append(group_index)
    for schedule_rule in solver_input.schedule_rules:
        if schedule_rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES:
            rule_allowed_waves = set(schedule_rule.waves)
            for player_id in schedule_rule.player_ids:
                for group_index in group_indices_by_player[player_id]:
                    for wave_no in waves:
                        if wave_no not in rule_allowed_waves:
                            for team_index, _team in enumerate(teams):
                                model.add(
                                    group_assignment[group_index, wave_no, team_index] == 0
                                )
        elif schedule_rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES:
            for player_id in schedule_rule.player_ids:
                for group_index in group_indices_by_player[player_id]:
                    for wave_no in schedule_rule.waves:
                        for team_index, _team in enumerate(teams):
                            model.add(
                                group_assignment[group_index, wave_no, team_index] == 0
                            )
        elif schedule_rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
            player_ids = set(schedule_rule.player_ids)
            for wave_no in waves:
                model.add(
                    sum(
                        group_assignment[group_index, wave_no, team_index]
                        for player_id in player_ids
                        for group_index in group_indices_by_player[player_id]
                        for team_index, _team in enumerate(teams)
                    )
                    <= 1
                )
    preference_by_player = {
        preference.player_id: preference for preference in solver_input.player_preferences
    }
    for player_id, group_indices in group_indices_by_player.items():
        for wave_no in waves:
            model.add(
                sum(
                    group_assignment[group_index, wave_no, team_index]
                    for group_index in group_indices
                    for team_index, _team in enumerate(teams)
                )
                <= 1
            )
        preference = preference_by_player.get(player_id)
        if preference is not None and preference.max_wave_count is not None:
            model.add(
                sum(
                    group_assignment[group_index, wave_no, team_index]
                    for group_index in group_indices
                    for wave_no in waves
                    for team_index, _team in enumerate(teams)
                )
                <= preference.max_wave_count
            )

    locked_empty_counts: dict[tuple[int, str], int] = defaultdict(int)
    for locked_empty in solver_input.locked_empty_slots:
        locked_empty_counts[locked_empty.wave_no, locked_empty.team_key] += locked_empty.count
    composition_rules = solver_input.dungeon.composition_rules.allowed
    composition_penalties: list[cp_model.LinearExpr] = []
    team_full: dict[tuple[int, int], cp_model.IntVar] = {}
    for wave_no in waves:
        for team_index, team in enumerate(teams):
            member_count = sum(
                group_assignment[group_index, wave_no, team_index]
                for group_index, _group_key in enumerate(group_keys)
            )
            effective_capacity = team.member_count - locked_empty_counts[wave_no, team.team_key]
            model.add(member_count <= effective_capacity)
            full = model.new_bool_var(f"target_team_full_{wave_no}_{team_index}")
            model.add(member_count == team.member_count).only_enforce_if(full)
            model.add(member_count <= team.member_count - 1).only_enforce_if(~full)
            team_full[wave_no, team_index] = full
            selections: list[cp_model.IntVar] = []
            for rule_index, rule in enumerate(composition_rules):
                if team.team_key not in rule.applicable_team_keys:
                    continue
                selection = model.new_bool_var(
                    f"target_composition_{wave_no}_{team_index}_{rule_index}"
                )
                selections.append(selection)
                composition_penalties.append((rule.priority - 1) * selection)
                for role_type in RoleType:
                    role_count = sum(
                        group_assignment[group_index, wave_no, team_index]
                        for group_index, group_key in enumerate(group_keys)
                        if group_key[1] == role_type
                    )
                    model.add(role_count == rule.roles.get(role_type, 0)).only_enforce_if(
                        selection
                    )
            model.add(sum(selections) == full)

    buffer_targets = _buffer_count_targets(solver_input)
    for (wave_no, team_key), target_count in buffer_targets.items():
        team_index = team_index_by_key[team_key]
        model.add(
            sum(
                group_assignment[group_index, wave_no, team_index]
                for group_index, group_key in enumerate(group_keys)
                if group_key[1] == RoleType.BUFFER
            )
            == target_count
        )
    damage_rule = (
        solver_input.dungeon.optimization_rules.damage_placement
        if buffer_targets
        else None
    )
    if damage_rule is not None:
        primary_team_index = team_index_by_key[damage_rule.primary_team_key]
        primary_capacity = teams[primary_team_index].member_count
        for wave_no in waves:
            model.add(
                sum(
                    group_assignment[group_index, wave_no, primary_team_index]
                    for group_index, group_key in enumerate(group_keys)
                    if group_key[1] == RoleType.DAMAGE
                )
                == primary_capacity
                - buffer_targets[wave_no, damage_rule.primary_team_key]
            )

    assigned_total = cp_model.LinearExpr.sum(list(group_assignment.values()))
    model.add(assigned_total <= assignment_target)
    wave_full: dict[int, cp_model.IntVar] = {}
    for wave_no in waves:
        full = model.new_bool_var(f"target_wave_full_{wave_no}")
        full_teams = [team_full[wave_no, team_index] for team_index, _team in enumerate(teams)]
        model.add_bool_and(full_teams).only_enforce_if(full)
        model.add_bool_or([~team_full_var for team_full_var in full_teams]).only_enforce_if(
            ~full
        )
        wave_full[wave_no] = full
    treasure_used: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for group_index, group_key in enumerate(group_keys):
        treasure_count = sum(
            participants[participant_index].is_treasure_damage
            for participant_index in participant_indices_by_group[group_key]
        )
        if treasure_count == 0:
            continue
        group_treasure_variables: list[cp_model.IntVar] = []
        for wave_no in waves:
            for team_index, _team in enumerate(teams):
                variable = model.new_bool_var(
                    f"target_treasure_{group_index}_{wave_no}_{team_index}"
                )
                model.add(variable <= group_assignment[group_index, wave_no, team_index])
                treasure_used[group_index, wave_no, team_index] = variable
                group_treasure_variables.append(variable)
        model.add(sum(group_treasure_variables) <= treasure_count)
    for (group_index, wave_no, team_index), identities in (
        identities_by_group_position.items()
    ):
        treasure_variable = treasure_used.get((group_index, wave_no, team_index))
        if treasure_variable is None:
            continue
        treasure_identities = [
            variable
            for participant_index, variable in identities
            if participants[participant_index].is_treasure_damage
        ]
        non_treasure_identities = [
            variable
            for participant_index, variable in identities
            if not participants[participant_index].is_treasure_damage
        ]
        if treasure_identities:
            model.add(treasure_variable >= sum(treasure_identities))
        if non_treasure_identities:
            model.add(
                treasure_variable + sum(non_treasure_identities)
                <= group_assignment[group_index, wave_no, team_index]
            )
    for locked in solver_input.locked_assignments:
        participant_index = participant_index_by_id[locked.participant_id]
        group_index = group_index_by_key[group_key_by_participant[participant_index]]
        treasure_variable = treasure_used.get(
            (group_index, locked.wave_no, team_index_by_key[locked.team_key])
        )
        if treasure_variable is not None:
            model.add(
                treasure_variable
                == int(participants[participant_index].is_treasure_damage)
            )

    special_satisfied: list[cp_model.IntVar] = []
    for rule_index, special_rule in enumerate(solver_input.dungeon.special_role_rules.rules):
        target_team_index = team_index_by_key[special_rule.target_team_key]
        for wave_no in waves:
            special_count = sum(
                variable
                for (group_index, candidate_wave, team_index), variable in treasure_used.items()
                if candidate_wave == wave_no
                and team_index == target_team_index
                and group_keys[group_index][1] == RoleType.DAMAGE
            )
            model.add(special_count <= special_rule.count_per_wave)
            satisfied = model.new_bool_var(f"target_special_{rule_index}_{wave_no}")
            model.add(special_count == special_rule.count_per_wave * satisfied)
            model.add(satisfied <= wave_full[wave_no])
            special_satisfied.append(satisfied)
    composition_penalty = cp_model.LinearExpr.sum(composition_penalties)
    special_total = cp_model.LinearExpr.sum(special_satisfied)
    special_upper_bound = len(special_satisfied)
    composition_penalty_upper_bound = sum(
        max(0, rule.priority - 1)
        for _wave_no in waves
        for team in teams
        for rule in composition_rules
        if team.team_key in rule.applicable_team_keys
    )
    secondary_upper_bound = (
        (special_upper_bound + 1) * composition_penalty_upper_bound
        + special_upper_bound
    )
    model.maximize(
        (secondary_upper_bound + 1) * assigned_total
        - (special_upper_bound + 1) * composition_penalty
        + special_total
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.05, time_limit_seconds)
    solver.parameters.random_seed = solver_input.random_seed
    solver.parameters.num_search_workers = 8
    # Deterministic interleaving keeps the parallel aggregate search repeatable
    # for the same seed while retaining the dense-roster speedup.
    solver.parameters.interleave_search = True
    status = _status(solver.solve(model))
    if status not in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE):
        return None, solver.wall_time, 0

    hint = {
        (participant_index, wave_no, team_index): 0
        for participant_index, _participant in enumerate(participants)
        for wave_no in waves
        for team_index, _team in enumerate(teams)
    }
    identities_by_group: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    hint_score_by_role_wave: dict[tuple[RoleType, int], int] = defaultdict(int)
    for (participant_index, wave_no, team_index), variable in identity_assignment.items():
        if not solver.value(variable):
            continue
        group_index = group_index_by_key[group_key_by_participant[participant_index]]
        identities_by_group[group_index].append((participant_index, wave_no, team_index))
        participant = participants[participant_index]
        hint_score_by_role_wave[participant.role_type, wave_no] += participant.score
    for group_index, group_key in enumerate(group_keys):
        selected_positions = {
            (wave_no, team_index)
            for wave_no in waves
            for team_index, _team in enumerate(teams)
            if solver.value(group_assignment[group_index, wave_no, team_index])
        }
        locked_participant_indices: set[int] = set()
        for participant_index, wave_no, team_index in identities_by_group[group_index]:
            hint[participant_index, wave_no, team_index] = 1
            selected_positions.remove((wave_no, team_index))
            locked_participant_indices.add(participant_index)
        required_treasure_positions = {
            (wave_no, team_index)
            for wave_no, team_index in selected_positions
            if (
                treasure_hint_variable := treasure_used.get(
                    (group_index, wave_no, team_index)
                )
            )
            is not None
            and solver.value(treasure_hint_variable)
        }
        treasure_indices = iter(
            participant_index
            for participant_index in participant_indices_by_group[group_key]
            if participant_index not in locked_participant_indices
            and participants[participant_index].is_treasure_damage
        )
        for participant_index, (wave_no, team_index) in zip(
            treasure_indices, sorted(required_treasure_positions), strict=False
        ):
            hint[participant_index, wave_no, team_index] = 1
            selected_positions.remove((wave_no, team_index))
            locked_participant_indices.add(participant_index)
            participant = participants[participant_index]
            hint_score_by_role_wave[participant.role_type, wave_no] += participant.score
        available_indices = [
            participant_index
            for participant_index in participant_indices_by_group[group_key]
            if participant_index not in locked_participant_indices
        ][: len(selected_positions)]
        available_indices.sort(
            key=lambda participant_index: (
                -participants[participant_index].score,
                participants[participant_index].participant_id,
            )
        )
        role_team_ranks = team_rank_by_role.get(group_key[1], {})
        role_type = group_key[1]
        for participant_index in available_indices:
            wave_no, team_index = min(
                selected_positions,
                key=lambda position: (
                    role_team_ranks.get(teams[position[1]].team_key, len(teams)),
                    hint_score_by_role_wave[role_type, position[0]],
                    position[0],
                    position[1],
                ),
            )
            hint[participant_index, wave_no, team_index] = 1
            hint_score_by_role_wave[role_type, wave_no] += participants[
                participant_index
            ].score
            selected_positions.remove((wave_no, team_index))
    return hint, solver.wall_time, round(solver.value(assigned_total))


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
    if not 0 <= solver_input.damage_balance_tolerance_percent <= 100:
        raise ValueError("damage_balance_tolerance_percent 必须位于 0..100")
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
    if len({rule.rule_id for rule in solver_input.schedule_rules}) != len(
        solver_input.schedule_rules
    ):
        raise ValueError("schedule_rules 中的 rule_id 必须唯一")
    player_rule_types = {
        SolverScheduleRuleType.PLAYER_ALLOWED_WAVES,
        SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES,
        SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE,
        SolverScheduleRuleType.PLAYER_PREFER_CONTIGUOUS,
    }
    character_rule_types = {
        SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE,
        SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM,
        SolverScheduleRuleType.CHARACTER_PREFER_TEAM,
    }
    wave_rule_types = {
        SolverScheduleRuleType.PLAYER_ALLOWED_WAVES,
        SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES,
        SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE,
        SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE,
    }
    team_rule_types = {
        SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM,
        SolverScheduleRuleType.CHARACTER_PREFER_TEAM,
    }
    for rule in solver_input.schedule_rules:
        if rule.type in player_rule_types:
            if len(rule.player_ids) != 1 or rule.player_ids[0] not in player_ids:
                raise ValueError("schedule_rules 引用了未知或数量错误的玩家")
        elif rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE and (
            len(rule.player_ids) < 2 or not set(rule.player_ids) <= player_ids
        ):
            raise ValueError("PLAYERS_NOT_SAME_WAVE 至少需要两个已知玩家")
        if rule.type in character_rule_types and rule.participant_id not in participant_ids:
            raise ValueError("schedule_rules 引用了未知角色")
        if rule.type in wave_rule_types and (
            not rule.waves
            or any(not 1 <= wave_no <= solver_input.wave_count for wave_no in rule.waves)
        ):
            raise ValueError("schedule_rules 包含空或越界波次")
        if rule.type in team_rule_types and rule.team_key not in team_keys:
            raise ValueError("schedule_rules 引用了未知队伍")
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
    if definition.optimization_rules.buffer_placement is not None:
        _buffer_count_targets(solver_input)
    if definition.optimization_rules.damage_placement is not None:
        average_factor = _damage_average_scale(solver_input) * 100
        if total_score > INT64_MAX // average_factor:
            raise ValueError("C 平均伤害目标的最坏情况超过有符号 64 位整数范围")
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
    if status_code == cp_model.UNKNOWN:
        return SolverStatus.TIMEOUT
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
    assignments: list[SolverAssignment],
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
    assignment_by_participant = {
        assignment.participant_id: (assignment.wave_no, assignment.team_key)
        for assignment in assignments
    }
    buffer_targets = _buffer_count_targets(solver_input)
    target_composition_count = sum(
        summary in complete_teams
        and summary.role_counts[RoleType.BUFFER]
        == buffer_targets.get((summary.wave_no, summary.team_key))
        for summary in summaries
        if (summary.wave_no, summary.team_key) in buffer_targets
    )
    team_index_by_key = {
        team.team_key: index for index, team in enumerate(solver_input.dungeon.teams)
    }
    buffer_placement_count = sum(
        assignment_by_participant.get(
            solver_input.participants[participant_index].participant_id
        )
        == (wave_no, solver_input.dungeon.teams[team_index].team_key)
        for participant_index, wave_no, team_index in _build_buffer_placement_targets(
            solver_input, team_index_by_key
        )
    )
    damage_primary_count = 0
    damage_pair_count = 0
    damage_pair_wave_count = 0
    damage_balance_spread = 0
    damage_balance_tolerance_excess = 0
    damage_balance_percent = 0
    damage_rule = (
        solver_input.dungeon.optimization_rules.damage_placement
        if buffer_targets
        else None
    )
    if damage_rule is not None:
        primary_team = next(
            team
            for team in solver_input.dungeon.teams
            if team.team_key == damage_rule.primary_team_key
        )
        primary_slot_count = sum(
            primary_team.member_count
            - buffer_targets[wave_no, damage_rule.primary_team_key]
            for wave_no in range(1, solver_input.wave_count + 1)
        )
        selected_damage = sorted(
            (
                participant
                for participant in solver_input.participants
                if participant.role_type == RoleType.DAMAGE
            ),
            key=lambda participant: (-participant.score, participant.participant_id),
        )[:primary_slot_count]
        damage_primary_count = sum(
            assignment_by_participant.get(participant.participant_id, (None, None))[1]
            == damage_rule.primary_team_key
            for participant in selected_damage
        )
        remaining_damage = list(selected_damage)
        minimum_primary_buffers = _buffer_count_bounds(solver_input)[
            damage_rule.primary_team_key
        ][0]
        for wave_no in range(1, solver_input.wave_count + 1):
            if (
                buffer_targets[wave_no, damage_rule.primary_team_key]
                <= minimum_primary_buffers
                or len(remaining_damage) < 2
            ):
                continue
            damage_pair_wave_count += 1
            strongest = remaining_damage.pop(0)
            weakest = remaining_damage.pop()
            damage_pair_count += (
                assignment_by_participant.get(strongest.participant_id)
                == (wave_no, damage_rule.primary_team_key)
                and assignment_by_participant.get(weakest.participant_id)
                == (wave_no, damage_rule.primary_team_key)
            )

        average_scale = _damage_average_scale(solver_input)
        balanced_averages = [
            summary.damage_total * average_scale // summary.role_counts[RoleType.DAMAGE]
            for summary in complete_teams
            if summary.team_key in damage_rule.balanced_team_keys
            and summary.role_counts[RoleType.DAMAGE] > 0
        ]
        if balanced_averages:
            minimum_average = min(balanced_averages)
            maximum_average = max(balanced_averages)
            damage_balance_spread = maximum_average - minimum_average
            damage_balance_tolerance_excess = max(
                0,
                100 * maximum_average
                - (100 + solver_input.damage_balance_tolerance_percent)
                * minimum_average,
            )
            damage_balance_percent = (
                (damage_balance_spread * 100 + minimum_average - 1)
                // minimum_average
                if minimum_average
                else 0
                if maximum_average == 0
                else 100
            )
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
        target_composition_count=target_composition_count,
        buffer_placement_count=buffer_placement_count,
        damage_primary_count=damage_primary_count,
        damage_pair_count=damage_pair_count,
        damage_pair_wave_count=damage_pair_wave_count,
        damage_balance_spread=damage_balance_spread,
        damage_balance_tolerance_excess=damage_balance_tolerance_excess,
        damage_balance_percent=damage_balance_percent,
        damage_average_scale=_damage_average_scale(solver_input),
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
    objective_summary: ObjectiveSummary,
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
    buffer_target_count = len(
        _build_buffer_placement_targets(
            solver_input,
            {
                team.team_key: index
                for index, team in enumerate(solver_input.dungeon.teams)
            },
        )
    )
    if objective_summary.buffer_placement_count < buffer_target_count:
        issues.append(
            SolverIssue(
                "WARNING",
                "BUFFER_PLACEMENT_DEVIATION",
                {
                    "target": buffer_target_count,
                    "current": objective_summary.buffer_placement_count,
                },
            )
        )
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
    damage_rule = (
        solver_input.dungeon.optimization_rules.damage_placement
        if _buffer_count_targets(solver_input)
        else None
    )
    if damage_rule is not None:
        primary_team = next(
            team
            for team in solver_input.dungeon.teams
            if team.team_key == damage_rule.primary_team_key
        )
        primary_target = sum(
            primary_team.member_count
            - _buffer_count_targets(solver_input)[wave_no, damage_rule.primary_team_key]
            for wave_no in range(1, solver_input.wave_count + 1)
        )
        if objective_summary.damage_primary_count < primary_target:
            issues.append(
                SolverIssue(
                    "WARNING",
                    "DAMAGE_PRIMARY_SELECTION_DEVIATION",
                    {
                        "teamKey": damage_rule.primary_team_key,
                        "target": primary_target,
                        "current": objective_summary.damage_primary_count,
                    },
                )
            )
        buffer_targets = _buffer_count_targets(solver_input)
        minimum_primary_buffers = _buffer_count_bounds(solver_input)[
            damage_rule.primary_team_key
        ][0]
        pair_target = sum(
            buffer_targets[wave_no, damage_rule.primary_team_key]
            > minimum_primary_buffers
            for wave_no in range(1, solver_input.wave_count + 1)
        )
        if (
            damage_rule.pair_extremes_in_double_buffer_teams
            and objective_summary.damage_pair_count < pair_target
        ):
            issues.append(
                SolverIssue(
                    "WARNING",
                    "DAMAGE_PAIRING_DEVIATION",
                    {
                        "target": pair_target,
                        "current": objective_summary.damage_pair_count,
                    },
                )
            )
        balanced = [
            summary
            for summary in summaries
            if summary.member_count == team_by_key[summary.team_key].member_count
            and summary.composition_code is not None
            and summary.team_key in damage_rule.balanced_team_keys
            and summary.role_counts[RoleType.DAMAGE] > 0
        ]
        scale = _damage_average_scale(solver_input)
        averages = [
            summary.damage_total * scale // summary.role_counts[RoleType.DAMAGE]
            for summary in balanced
        ]
        if averages:
            minimum = min(averages)
            maximum = max(averages)
            actual_percent = (
                ((maximum - minimum) * 100 + minimum - 1) // minimum
                if minimum
                else 0
                if maximum == 0
                else 100
            )
            if actual_percent > solver_input.damage_balance_tolerance_percent:
                issues.append(
                    SolverIssue(
                        "WARNING",
                        "DAMAGE_BALANCE_TOLERANCE_EXCEEDED",
                        {
                            "teamKeys": list(damage_rule.balanced_team_keys),
                            "configuredPercent": solver_input.damage_balance_tolerance_percent,
                            "actualPercent": actual_percent,
                        },
                    )
                )
    return tuple(issues)
