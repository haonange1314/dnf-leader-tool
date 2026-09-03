from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.domain.schedule.rules import (
    RuleContextParticipant,
    RuleContextTeam,
    RuleInterpretationContext,
    RuleResolutionIssue,
    compile_resolved_rules,
    rule_context_hash,
)
from app.integrations.deepseek_rules import DeepSeekRuleProvider
from app.models.identity import NaturalLanguageRateLimit
from app.models.schedule import Schedule, ScheduleRuleSet
from app.solver import SolverScheduleRule


def build_rule_context(schedule: Schedule) -> RuleInterpretationContext:
    preference_by_player = {
        preference.player_id: preference for preference in schedule.preferences
    }
    first_wave = min(schedule.waves, key=lambda wave: wave.wave_no, default=None)
    teams = (
        tuple(
            RuleContextTeam(team.team_key, team.display_name_snapshot)
            for team in sorted(
                first_wave.teams, key=lambda team: team.display_order_snapshot
            )
        )
        if first_wave is not None
        else ()
    )
    ranked_teams = (
        [team for team in first_wave.teams if team.strength_rank_snapshot is not None]
        if first_wave is not None
        else []
    )
    lead_team_keys = None
    if ranked_teams:
        lead_rank = min(
            team.strength_rank_snapshot
            for team in ranked_teams
            if team.strength_rank_snapshot is not None
        )
        lead_team_keys = tuple(
            team.team_key
            for team in ranked_teams
            if team.strength_rank_snapshot == lead_rank
        )

    selected = tuple(
        RuleContextParticipant(
            participant_id=str(participant.id),
            player_id=str(participant.player_id_snapshot),
            player_name=participant.player_name_snapshot,
            character_name=participant.character_name_snapshot,
            profession=participant.profession_snapshot,
            role_type=participant.role_type_snapshot,
            is_treasure_damage=participant.is_treasure_snapshot,
            is_group_hunt=participant.is_group_hunt_snapshot,
            allowed_waves=(
                tuple(
                    sorted(
                        preference_by_player[
                            participant.player_id_snapshot
                        ].allowed_waves
                        or []
                    )
                )
                if participant.player_id_snapshot in preference_by_player
                and preference_by_player[participant.player_id_snapshot].allowed_waves
                is not None
                else None
            ),
            max_wave_count=(
                preference_by_player[participant.player_id_snapshot].max_wave_count
                if participant.player_id_snapshot in preference_by_player
                else None
            ),
            allowed_team_keys=(
                lead_team_keys
                if participant.is_fixed_lead_team_buffer_snapshot
                else None
            ),
        )
        for participant in schedule.participants
        if participant.is_selected
    )
    return RuleInterpretationContext(
        schedule_id=str(schedule.id),
        revision=schedule.revision,
        wave_count=schedule.wave_count,
        participants=selected,
        teams=teams,
    )


def build_rule_provider(settings: Settings) -> DeepSeekRuleProvider:
    if not settings.natural_language_rules_enabled or settings.deepseek_api_key is None:
        raise ValueError("自然语言排表规则尚未启用")
    return DeepSeekRuleProvider(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )


def consume_rule_parse_quota(
    db: Session,
    user_id: uuid.UUID,
    settings: Settings,
) -> None:
    now = utc_now()
    window = timedelta(
        seconds=settings.natural_language_rule_rate_limit_window_seconds
    )
    lock_digest = hashlib.sha256(f"rule-parse|{user_id}".encode()).hexdigest()
    lock_key = int(lock_digest[:16], 16)
    if lock_key >= 2**63:
        lock_key -= 2**64
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    db.execute(
        delete(NaturalLanguageRateLimit).where(
            NaturalLanguageRateLimit.updated_at < now - window * 2
        )
    )
    row = db.scalar(
        select(NaturalLanguageRateLimit)
        .where(NaturalLanguageRateLimit.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        db.add(
            NaturalLanguageRateLimit(
                user_id=user_id,
                request_count=1,
                window_started_at=now,
                updated_at=now,
            )
        )
        return
    if now - row.window_started_at >= window:
        row.request_count = 1
        row.window_started_at = now
        row.updated_at = now
        return
    if row.request_count >= settings.natural_language_rule_rate_limit_requests:
        retry_after = max(
            1,
            int((row.window_started_at + window - now).total_seconds()),
        )
        raise AppError(
            429,
            "RULE_PARSE_RATE_LIMITED",
            "自然语言规则解析请求过于频繁，请稍后重试",
            details={"retryAfterSeconds": retry_after},
        )
    row.request_count += 1
    row.updated_at = now


def serialize_resolution_issues(
    issues: tuple[RuleResolutionIssue, ...],
) -> list[dict[str, object]]:
    return [
        {
            "code": issue.code,
            "candidateId": issue.candidate_id,
            "field": issue.field,
            "reference": issue.reference,
            "matches": list(issue.matches),
        }
        for issue in issues
    ]


def compile_rule_set(rule_set: ScheduleRuleSet | None) -> tuple[SolverScheduleRule, ...]:
    if rule_set is None or rule_set.status != "CONFIRMED":
        return ()
    return compile_resolved_rules(rule_set.parsed_rules)


def active_rule_set_context_is_current(schedule: Schedule) -> bool:
    rule_set = schedule.active_rule_set
    return rule_set is None or rule_set.context_hash == rule_context_hash(
        build_rule_context(schedule)
    )


def invalidate_active_rule_set(schedule: Schedule) -> None:
    if schedule.active_rule_set is not None:
        schedule.active_rule_set.status = "STALE"
    schedule.active_rule_set_id = None
