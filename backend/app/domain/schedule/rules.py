from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from app.schemas.schedule_rules import RuleCandidate, RuleProviderOutput
from app.solver.models import (
    LockedAssignment,
    SolverAssignment,
    SolverParticipant,
    SolverScheduleRule,
    SolverScheduleRuleType,
)

RULE_COMPILER_VERSION = "schedule-rules-v1"

HARD_RULE_TYPES = frozenset(
    {
        SolverScheduleRuleType.PLAYER_ALLOWED_WAVES,
        SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES,
        SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE,
        SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE,
        SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM,
    }
)


@dataclass(frozen=True, slots=True)
class RuleContextParticipant:
    participant_id: str
    player_id: str
    player_name: str
    character_name: str
    profession: str
    role_type: str
    is_treasure_damage: bool = False
    is_group_hunt: bool = False


@dataclass(frozen=True, slots=True)
class RuleContextTeam:
    team_key: str
    display_name: str


@dataclass(frozen=True, slots=True)
class RuleInterpretationContext:
    schedule_id: str
    revision: int
    wave_count: int
    participants: tuple[RuleContextParticipant, ...]
    teams: tuple[RuleContextTeam, ...]


@dataclass(frozen=True, slots=True)
class RuleResolutionIssue:
    code: str
    candidate_id: str | None
    field: str | None
    reference: str | None
    matches: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedRuleSet:
    rules: tuple[dict[str, Any], ...]
    resolved_references: dict[str, Any]
    issues: tuple[RuleResolutionIssue, ...]


def rule_context_hash(context: RuleInterpretationContext) -> str:
    payload = {
        "scheduleId": context.schedule_id,
        "waveCount": context.wave_count,
        "participants": [asdict(participant) for participant in context.participants],
        "teams": [asdict(team) for team in context.teams],
        "capabilities": sorted(rule_type.value for rule_type in SolverScheduleRuleType),
        "compilerVersion": RULE_COMPILER_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_text_hash(source_text: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", source_text).split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def resolve_rule_output(
    output: RuleProviderOutput,
    context: RuleInterpretationContext,
) -> ResolvedRuleSet:
    issues: list[RuleResolutionIssue] = []
    rules: list[dict[str, Any]] = []
    references: dict[str, Any] = {}
    seen_candidate_ids: set[str] = set()

    for unsupported in output.unsupported_items:
        issues.append(
            RuleResolutionIssue(
                code="RULE_SET_TYPE_UNSUPPORTED",
                candidate_id=None,
                field=None,
                reference=unsupported,
            )
        )

    for candidate in output.rules:
        candidate_id = candidate.candidate_id
        if candidate_id in seen_candidate_ids:
            issues.append(
                RuleResolutionIssue(
                    code="RULE_SET_CANDIDATE_DUPLICATED",
                    candidate_id=candidate_id,
                    field="candidateId",
                    reference=candidate_id,
                )
            )
            continue
        seen_candidate_ids.add(candidate_id)
        resolved, candidate_references, candidate_issues = _resolve_candidate(candidate, context)
        issues.extend(candidate_issues)
        if candidate_issues:
            continue
        rules.append(resolved)
        references[candidate_id] = candidate_references

    issues.extend(_hard_conflict_issues(tuple(rules), context))
    return ResolvedRuleSet(tuple(rules), references, tuple(issues))


def compile_resolved_rules(
    rules: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> tuple[SolverScheduleRule, ...]:
    compiled: list[SolverScheduleRule] = []
    for rule in rules:
        rule_type = SolverScheduleRuleType(rule["type"])
        compiled.append(
            SolverScheduleRule(
                rule_id=str(rule["candidateId"]),
                type=rule_type,
                explanation=str(rule["explanation"]),
                player_ids=tuple(str(item) for item in rule.get("playerIds", [])),
                participant_id=(str(rule["participantId"]) if rule.get("participantId") else None),
                waves=tuple(int(item) for item in rule.get("waves", [])),
                team_key=str(rule["teamKey"]) if rule.get("teamKey") else None,
            )
        )
    return tuple(compiled)


def evaluate_compiled_rules(
    rules: tuple[SolverScheduleRule, ...],
    assignments: tuple[SolverAssignment, ...],
    participants: tuple[SolverParticipant, ...],
) -> list[dict[str, Any]]:
    locations = {
        assignment.participant_id: (
            assignment.wave_no,
            assignment.team_key,
        )
        for assignment in assignments
    }
    player_by_participant = {
        participant.participant_id: participant.player_id for participant in participants
    }
    player_waves: dict[str, set[int]] = {}
    for participant_id, (wave_no, _team_key) in locations.items():
        player_waves.setdefault(player_by_participant[participant_id], set()).add(wave_no)

    evaluations: list[dict[str, Any]] = []
    for rule in rules:
        satisfied = _is_rule_satisfied(rule, locations, player_waves)
        evaluations.append(
            {
                "ruleId": rule.rule_id,
                "type": rule.type.value,
                "status": "SATISFIED" if satisfied else "UNSATISFIED",
                "explanation": rule.explanation,
            }
        )
    return evaluations


def evaluate_locked_rule_blockers(
    rules: tuple[SolverScheduleRule, ...],
    locked_assignments: tuple[LockedAssignment, ...],
    participants: tuple[SolverParticipant, ...],
) -> dict[str, str]:
    """Return confirmed hard rules that directly conflict with preserved locks."""
    player_by_participant = {
        participant.participant_id: participant.player_id for participant in participants
    }
    blockers: dict[str, str] = {}
    for rule in rules:
        if rule.type not in HARD_RULE_TYPES:
            continue
        targeted_locks = tuple(
            locked
            for locked in locked_assignments
            if (
                locked.participant_id == rule.participant_id
                or player_by_participant.get(locked.participant_id) in rule.player_ids
            )
        )
        if rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES and any(
            locked.wave_no not in rule.waves for locked in targeted_locks
        ):
            blockers[rule.rule_id] = "已锁定角色位于该玩家允许波次之外"
        elif rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES and any(
            locked.wave_no in rule.waves for locked in targeted_locks
        ):
            blockers[rule.rule_id] = "已锁定角色位于该玩家禁止参加的波次"
        elif rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
            player_ids_by_wave: dict[int, set[str]] = {}
            for locked in targeted_locks:
                player_id = player_by_participant.get(locked.participant_id)
                if player_id in rule.player_ids:
                    player_ids_by_wave.setdefault(locked.wave_no, set()).add(player_id)
            if any(len(player_ids) > 1 for player_ids in player_ids_by_wave.values()):
                blockers[rule.rule_id] = "互斥玩家已有角色被锁定在同一波"
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE and any(
            locked.wave_no not in rule.waves for locked in targeted_locks
        ):
            blockers[rule.rule_id] = "该角色已被锁定在其他波次"
        elif rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM and any(
            locked.team_key != rule.team_key for locked in targeted_locks
        ):
            blockers[rule.rule_id] = "该角色已被锁定在其他队伍"
    return blockers


def blocked_generation_rule_evaluation(
    rules: tuple[SolverScheduleRule, ...],
    blockers: dict[str, str] | None = None,
    *,
    reason: str = "当前副本约束、候选角色或锁定安排无法形成可行解",
) -> list[dict[str, Any]]:
    blocker_reasons = blockers or {}
    evaluations: list[dict[str, Any]] = []
    for rule in rules:
        blocked = rule.rule_id in blocker_reasons or (
            not blocker_reasons and rule.type in HARD_RULE_TYPES
        )
        evaluations.append(
            {
                "ruleId": rule.rule_id,
                "type": rule.type.value,
                "status": "BLOCKED" if blocked else "NOT_APPLICABLE",
                "explanation": rule.explanation,
                "reason": blocker_reasons.get(
                    rule.rule_id,
                    reason if blocked else "求解未执行或未产生可评价的排表",
                ),
            }
        )
    return evaluations


def _resolve_candidate(
    candidate: RuleCandidate,
    context: RuleInterpretationContext,
) -> tuple[dict[str, Any], dict[str, Any], list[RuleResolutionIssue]]:
    dumped = candidate.model_dump(mode="json", by_alias=True)
    resolved: dict[str, Any] = {
        "candidateId": candidate.candidate_id,
        "type": candidate.type,
        "enforcement": candidate.enforcement,
        "explanation": candidate.explanation,
    }
    references: dict[str, Any] = {}
    issues: list[RuleResolutionIssue] = []

    if "playerReference" in dumped and dumped["playerReference"] is not None:
        player = _resolve_player(
            dumped["playerReference"]["text"], candidate.candidate_id, "playerReference", context
        )
        if isinstance(player, RuleResolutionIssue):
            issues.append(player)
        else:
            resolved["playerIds"] = [player.player_id]
            references["player"] = {"id": player.player_id, "name": player.player_name}

    if "playerReferences" in dumped:
        players: list[RuleContextParticipant] = []
        for index, reference in enumerate(dumped["playerReferences"]):
            player = _resolve_player(
                reference["text"],
                candidate.candidate_id,
                f"playerReferences.{index}",
                context,
            )
            if isinstance(player, RuleResolutionIssue):
                issues.append(player)
            else:
                players.append(player)
        player_ids = tuple(dict.fromkeys(player.player_id for player in players))
        if not issues and len(player_ids) < 2:
            issues.append(
                RuleResolutionIssue(
                    "RULE_SET_REFERENCE_AMBIGUOUS",
                    candidate.candidate_id,
                    "playerReferences",
                    None,
                    player_ids,
                )
            )
        resolved["playerIds"] = list(player_ids)
        references["players"] = [
            {"id": player.player_id, "name": player.player_name} for player in players
        ]

    if "characterReference" in dumped:
        player_id = (resolved.get("playerIds") or [None])[0]
        participant = _resolve_character(
            dumped["characterReference"]["text"],
            candidate.candidate_id,
            context,
            player_id=player_id,
        )
        if isinstance(participant, RuleResolutionIssue):
            issues.append(participant)
        else:
            resolved["participantId"] = participant.participant_id
            references["participant"] = {
                "id": participant.participant_id,
                "playerId": participant.player_id,
                "playerName": participant.player_name,
                "profession": participant.profession,
            }

    if "teamReference" in dumped:
        team = _resolve_team(dumped["teamReference"]["text"], candidate.candidate_id, context)
        if isinstance(team, RuleResolutionIssue):
            issues.append(team)
        else:
            resolved["teamKey"] = team.team_key
            references["team"] = {"key": team.team_key, "name": team.display_name}

    waves = dumped.get("waves")
    if waves is not None:
        normalized_waves = sorted(set(int(wave) for wave in waves))
        invalid_waves = [wave for wave in normalized_waves if not 1 <= wave <= context.wave_count]
        if invalid_waves:
            issues.append(
                RuleResolutionIssue(
                    "RULE_SET_WAVE_OUT_OF_RANGE",
                    candidate.candidate_id,
                    "waves",
                    ",".join(str(wave) for wave in invalid_waves),
                )
            )
        resolved["waves"] = normalized_waves

    if "waveNo" in dumped:
        wave_no = int(dumped["waveNo"])
        if not 1 <= wave_no <= context.wave_count:
            issues.append(
                RuleResolutionIssue(
                    "RULE_SET_WAVE_OUT_OF_RANGE",
                    candidate.candidate_id,
                    "waveNo",
                    str(wave_no),
                )
            )
        resolved["waves"] = [wave_no]

    if "waveRange" in dumped:
        wave_range = dumped["waveRange"]
        start, end = int(wave_range["start"]), int(wave_range["end"])
        if start < 1 or end > context.wave_count:
            issues.append(
                RuleResolutionIssue(
                    "RULE_SET_WAVE_OUT_OF_RANGE",
                    candidate.candidate_id,
                    "waveRange",
                    f"{start}-{end}",
                )
            )
        resolved["waves"] = list(range(start, end + 1))

    return resolved, references, issues


def _resolve_player(
    text: str,
    candidate_id: str,
    field: str,
    context: RuleInterpretationContext,
) -> RuleContextParticipant | RuleResolutionIssue:
    key = _reference_key(text)
    matches_by_player: dict[str, RuleContextParticipant] = {}
    for participant in context.participants:
        if _reference_key(participant.player_name) == key:
            matches_by_player.setdefault(participant.player_id, participant)
    matches = tuple(matches_by_player.values())
    if len(matches) == 1:
        return matches[0]
    return RuleResolutionIssue(
        "RULE_SET_REFERENCE_NOT_FOUND" if not matches else "RULE_SET_REFERENCE_AMBIGUOUS",
        candidate_id,
        field,
        text,
        tuple(match.player_name for match in matches),
    )


def _resolve_character(
    text: str,
    candidate_id: str,
    context: RuleInterpretationContext,
    *,
    player_id: str | None,
) -> RuleContextParticipant | RuleResolutionIssue:
    key = _reference_key(text)
    matches = tuple(
        participant
        for participant in context.participants
        if (player_id is None or participant.player_id == player_id)
        and key
        in {
            _reference_key(participant.profession),
            _reference_key(participant.character_name),
        }
    )
    if len(matches) == 1:
        return matches[0]
    return RuleResolutionIssue(
        "RULE_SET_REFERENCE_NOT_FOUND" if not matches else "RULE_SET_REFERENCE_AMBIGUOUS",
        candidate_id,
        "characterReference",
        text,
        tuple(f"{match.player_name}/{match.profession}" for match in matches),
    )


def _resolve_team(
    text: str,
    candidate_id: str,
    context: RuleInterpretationContext,
) -> RuleContextTeam | RuleResolutionIssue:
    key = _reference_key(text)
    matches = tuple(
        team
        for team in context.teams
        if key in {_reference_key(team.team_key), _reference_key(team.display_name)}
    )
    if len(matches) == 1:
        return matches[0]
    return RuleResolutionIssue(
        "RULE_SET_REFERENCE_NOT_FOUND" if not matches else "RULE_SET_REFERENCE_AMBIGUOUS",
        candidate_id,
        "teamReference",
        text,
        tuple(match.display_name for match in matches),
    )


def _reference_key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _hard_conflict_issues(
    rules: tuple[dict[str, Any], ...],
    context: RuleInterpretationContext,
) -> tuple[RuleResolutionIssue, ...]:
    hard_rules = tuple(rule for rule in rules if rule["enforcement"] == "HARD")
    participant_players = {
        participant.participant_id: participant.player_id for participant in context.participants
    }
    issues: list[RuleResolutionIssue] = []
    seen: set[tuple[str, str]] = set()

    def add(rule: dict[str, Any], reason: str, related: list[str]) -> None:
        key = (str(rule["candidateId"]), reason)
        if key in seen:
            return
        seen.add(key)
        issues.append(
            RuleResolutionIssue(
                code="RULE_SET_HARD_CONFLICT",
                candidate_id=str(rule["candidateId"]),
                field=None,
                reference=reason,
                matches=tuple(related),
            )
        )

    for rule_type, value_key, label in (
        ("CHARACTER_REQUIRED_WAVE", "waves", "同一角色被要求进入不同波次"),
        ("CHARACTER_REQUIRED_TEAM", "teamKey", "同一角色被要求进入不同队伍"),
    ):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for rule in hard_rules:
            if rule["type"] == rule_type:
                grouped.setdefault(str(rule["participantId"]), []).append(rule)
        for grouped_rules in grouped.values():
            first = grouped_rules[0]
            for rule in grouped_rules[1:]:
                if rule[value_key] != first[value_key]:
                    add(rule, label, [str(first["candidateId"])])

    player_allowed: dict[str, list[dict[str, Any]]] = {}
    player_forbidden: dict[str, list[dict[str, Any]]] = {}
    for rule in hard_rules:
        target = (
            player_allowed
            if rule["type"] == "PLAYER_ALLOWED_WAVES"
            else player_forbidden
            if rule["type"] == "PLAYER_FORBIDDEN_WAVES"
            else None
        )
        if target is not None:
            for player_id in rule["playerIds"]:
                target.setdefault(str(player_id), []).append(rule)

    effective_allowed: dict[str, set[int]] = {}
    forbidden_waves: dict[str, set[int]] = {}
    for player_id, allowed_rules in player_allowed.items():
        allowed = set(int(wave) for wave in allowed_rules[0]["waves"])
        for rule in allowed_rules[1:]:
            allowed &= {int(wave) for wave in rule["waves"]}
        effective_allowed[player_id] = allowed
        if not allowed:
            add(
                allowed_rules[-1],
                "同一玩家的可参加波次没有交集",
                [str(rule["candidateId"]) for rule in allowed_rules[:-1]],
            )
    for player_id, forbidden_rules in player_forbidden.items():
        forbidden_waves[player_id] = {
            int(wave) for rule in forbidden_rules for wave in rule["waves"]
        }
        allowed_for_player = effective_allowed.get(player_id)
        if allowed_for_player and allowed_for_player <= forbidden_waves[player_id]:
            add(
                forbidden_rules[-1],
                "该玩家所有可参加波次同时被禁止",
                [str(rule["candidateId"]) for rule in player_allowed.get(player_id, [])],
            )

    required_by_player_wave: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for rule in hard_rules:
        if rule["type"] != "CHARACTER_REQUIRED_WAVE":
            continue
        player_id = participant_players[str(rule["participantId"])]
        wave_no = int(rule["waves"][0])
        required_by_player_wave.setdefault((player_id, wave_no), []).append(rule)
        required_allowed_waves = effective_allowed.get(player_id)
        if (
            required_allowed_waves is not None and wave_no not in required_allowed_waves
        ) or wave_no in forbidden_waves.get(player_id, set()):
            related = player_allowed.get(player_id, []) + player_forbidden.get(player_id, [])
            add(
                rule,
                "角色指定波次与玩家波次限制冲突",
                [str(item["candidateId"]) for item in related],
            )
    for required_rules in required_by_player_wave.values():
        participant_ids = {str(rule["participantId"]) for rule in required_rules}
        if len(participant_ids) > 1:
            add(
                required_rules[-1],
                "同一玩家的多个角色被要求进入同一波",
                [str(rule["candidateId"]) for rule in required_rules[:-1]],
            )

    required_waves_by_player: dict[str, set[int]] = {}
    for (player_id, wave_no), required_rules in required_by_player_wave.items():
        if required_rules:
            required_waves_by_player.setdefault(player_id, set()).add(wave_no)
    for rule in hard_rules:
        if rule["type"] != "PLAYERS_NOT_SAME_WAVE":
            continue
        player_ids = [str(player_id) for player_id in rule["playerIds"]]
        common_waves = set.intersection(
            *(required_waves_by_player.get(player_id, set()) for player_id in player_ids)
        )
        if common_waves:
            add(rule, "互斥玩家被指定进入同一波", [])

    return tuple(issues)


def _is_rule_satisfied(
    rule: SolverScheduleRule,
    locations: dict[str, tuple[int, str]],
    player_waves: dict[str, set[int]],
) -> bool:
    if rule.type == SolverScheduleRuleType.PLAYER_ALLOWED_WAVES:
        return all(
            player_waves.get(player_id, set()) <= set(rule.waves) for player_id in rule.player_ids
        )
    if rule.type == SolverScheduleRuleType.PLAYER_FORBIDDEN_WAVES:
        return all(
            not (player_waves.get(player_id, set()) & set(rule.waves))
            for player_id in rule.player_ids
        )
    if rule.type == SolverScheduleRuleType.PLAYERS_NOT_SAME_WAVE:
        counts: dict[int, int] = {}
        for player_id in rule.player_ids:
            for wave_no in player_waves.get(player_id, set()):
                counts[wave_no] = counts.get(wave_no, 0) + 1
        return all(count <= 1 for count in counts.values())
    if rule.type == SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE:
        return all(
            player_waves.get(player_id, set()) <= set(rule.waves) for player_id in rule.player_ids
        )
    if rule.type == SolverScheduleRuleType.PLAYER_PREFER_CONTIGUOUS:
        for player_id in rule.player_ids:
            waves = player_waves.get(player_id, set())
            if waves and max(waves) - min(waves) + 1 != len(waves):
                return False
        return True
    if rule.participant_id is None:
        return False
    location = locations.get(rule.participant_id)
    if location is None:
        return False
    if rule.type == SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE:
        return location[0] in rule.waves
    if rule.type in {
        SolverScheduleRuleType.CHARACTER_REQUIRED_TEAM,
        SolverScheduleRuleType.CHARACTER_PREFER_TEAM,
    }:
        return location[1] == rule.team_key
    return False
