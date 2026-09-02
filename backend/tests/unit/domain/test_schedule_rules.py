import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.domain.schedule.rules import (
    RuleContextParticipant,
    RuleContextTeam,
    RuleInterpretationContext,
    blocked_generation_rule_evaluation,
    compile_resolved_rules,
    evaluate_compiled_rules,
    evaluate_locked_rule_blockers,
    resolve_rule_output,
    rule_context_hash,
    source_text_hash,
)
from app.integrations.deepseek_rules import DeepSeekRuleProvider, RuleProviderError
from app.models.schedule import ScheduleRuleSet
from app.schemas.dungeon import RoleType
from app.schemas.schedule_rules import RuleProviderOutput, ScheduleRuleSetView
from app.solver import (
    LockedAssignment,
    SolverAssignment,
    SolverParticipant,
    SolverScheduleRule,
    SolverScheduleRuleType,
)


def _context() -> RuleInterpretationContext:
    return RuleInterpretationContext(
        schedule_id="schedule-1",
        revision=7,
        wave_count=12,
        participants=(
            RuleContextParticipant(
                "participant-1",
                "player-1",
                "韩亚",
                "剑魂",
                "剑魂",
                "DAMAGE",
            ),
            RuleContextParticipant(
                "participant-2",
                "player-2",
                "点评",
                "剑魂",
                "剑魂",
                "DAMAGE",
            ),
        ),
        teams=(RuleContextTeam("RED", "红队"), RuleContextTeam("YELLOW", "黄队")),
    )


def test_resolve_and_compile_supported_rules() -> None:
    output = RuleProviderOutput.model_validate(
        {
            "schemaVersion": 1,
            "rules": [
                {
                    "candidateId": "R1",
                    "type": "PLAYER_PREFER_WAVE_RANGE",
                    "enforcement": "SOFT",
                    "playerReference": {"text": " 韩亚 "},
                    "waveRange": {"start": 1, "end": 6},
                    "explanation": "韩亚优先前六波",
                },
                {
                    "candidateId": "R2",
                    "type": "CHARACTER_REQUIRED_TEAM",
                    "enforcement": "HARD",
                    "playerReference": {"text": "韩亚"},
                    "characterReference": {"text": "剑魂"},
                    "teamReference": {"text": "红队"},
                    "explanation": "韩亚的剑魂进入红队",
                },
            ],
            "unsupportedItems": [],
        }
    )

    resolved = resolve_rule_output(output, _context())
    compiled = compile_resolved_rules(resolved.rules)

    assert resolved.issues == ()
    assert resolved.rules[0]["playerIds"] == ["player-1"]
    assert resolved.rules[0]["waves"] == [1, 2, 3, 4, 5, 6]
    assert resolved.rules[1]["participantId"] == "participant-1"
    assert resolved.rules[1]["teamKey"] == "RED"
    assert compiled[0].type == SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE
    assert compiled[1].participant_id == "participant-1"


def test_ambiguous_character_and_unknown_rule_are_blocking_issues() -> None:
    output = RuleProviderOutput.model_validate(
        {
            "schemaVersion": 1,
            "rules": [
                {
                    "candidateId": "R1",
                    "type": "CHARACTER_REQUIRED_WAVE",
                    "enforcement": "HARD",
                    "characterReference": {"text": "剑魂"},
                    "waveNo": 13,
                    "explanation": "剑魂放第十三波",
                }
            ],
            "unsupportedItems": ["让模型随便排"],
        }
    )

    resolved = resolve_rule_output(output, _context())

    assert resolved.rules == ()
    assert {issue.code for issue in resolved.issues} == {
        "RULE_SET_TYPE_UNSUPPORTED",
        "RULE_SET_REFERENCE_AMBIGUOUS",
        "RULE_SET_WAVE_OUT_OF_RANGE",
    }


def test_directly_conflicting_hard_rules_are_blocked_before_confirmation() -> None:
    output = RuleProviderOutput.model_validate(
        {
            "schemaVersion": 1,
            "rules": [
                {
                    "candidateId": "R1",
                    "type": "CHARACTER_REQUIRED_WAVE",
                    "enforcement": "HARD",
                    "playerReference": {"text": "韩亚"},
                    "characterReference": {"text": "剑魂"},
                    "waveNo": 1,
                    "explanation": "韩亚剑魂第一波",
                },
                {
                    "candidateId": "R2",
                    "type": "PLAYER_FORBIDDEN_WAVES",
                    "enforcement": "HARD",
                    "playerReference": {"text": "韩亚"},
                    "waves": [1],
                    "explanation": "韩亚第一波不上",
                },
            ],
            "unsupportedItems": [],
        }
    )

    resolved = resolve_rule_output(output, _context())

    conflicts = [issue for issue in resolved.issues if issue.code == "RULE_SET_HARD_CONFLICT"]
    assert len(conflicts) == 1
    assert conflicts[0].candidate_id == "R1"
    assert conflicts[0].matches == ("R2",)


def test_context_and_source_hashes_are_stable_and_context_sensitive() -> None:
    context = _context()

    assert source_text_hash("  韩亚   前六波 ") == source_text_hash("韩亚 前六波")
    assert rule_context_hash(context) == rule_context_hash(context)
    assert rule_context_hash(context) != rule_context_hash(
        RuleInterpretationContext(
            schedule_id=context.schedule_id,
            revision=99,
            wave_count=11,
            participants=context.participants,
            teams=context.teams,
        )
    )


def test_schedule_rule_set_view_validates_an_orm_record() -> None:
    now = datetime.now(UTC)
    record = ScheduleRuleSet(
        id=uuid.uuid4(),
        schedule_id=uuid.uuid4(),
        input_revision=3,
        source_text="韩亚优先前六波",
        source_hash="a" * 64,
        context_hash="b" * 64,
        status="PARSED",
        model_provider="deepseek",
        model_name="deepseek-v4",
        provider_response_id=None,
        prompt_version="v1",
        schema_version=1,
        parsed_rules=[],
        resolved_references={},
        issues=[],
        created_by=uuid.uuid4(),
        confirmed_by=None,
        created_at=now,
        confirmed_at=None,
    )

    view = ScheduleRuleSetView.model_validate(record)

    assert view.id == record.id
    assert view.source_text == "韩亚优先前六波"


def test_player_soft_rules_are_evaluated_without_a_participant_reference() -> None:
    participants = (
        SolverParticipant("p-1", "player-1", RoleType.DAMAGE, 100),
        SolverParticipant("p-2", "player-1", RoleType.DAMAGE, 90),
    )
    rules = (
        SolverScheduleRule(
            "range",
            SolverScheduleRuleType.PLAYER_PREFER_WAVE_RANGE,
            "优先前两波",
            player_ids=("player-1",),
            waves=(1, 2),
        ),
        SolverScheduleRule(
            "contiguous",
            SolverScheduleRuleType.PLAYER_PREFER_CONTIGUOUS,
            "尽量连续上号",
            player_ids=("player-1",),
        ),
    )

    satisfied = evaluate_compiled_rules(
        rules,
        (
            SolverAssignment("p-1", 1, "RED"),
            SolverAssignment("p-2", 2, "RED"),
        ),
        participants,
    )
    unsatisfied = evaluate_compiled_rules(
        rules,
        (
            SolverAssignment("p-1", 1, "RED"),
            SolverAssignment("p-2", 3, "RED"),
        ),
        participants,
    )

    assert [item["status"] for item in satisfied] == ["SATISFIED", "SATISFIED"]
    assert [item["status"] for item in unsatisfied] == [
        "UNSATISFIED",
        "UNSATISFIED",
    ]


def test_locked_hard_rule_conflicts_have_rule_level_diagnostics() -> None:
    participants = (SolverParticipant("p-1", "player-1", RoleType.DAMAGE, 100),)
    rules = (
        SolverScheduleRule(
            "required-wave",
            SolverScheduleRuleType.CHARACTER_REQUIRED_WAVE,
            "该角色固定第二波",
            participant_id="p-1",
            waves=(2,),
        ),
        SolverScheduleRule(
            "prefer-team",
            SolverScheduleRuleType.CHARACTER_PREFER_TEAM,
            "优先红队",
            participant_id="p-1",
            team_key="RED",
        ),
    )

    blockers = evaluate_locked_rule_blockers(
        rules,
        (LockedAssignment("p-1", 1, "GREEN"),),
        participants,
    )
    evaluation = blocked_generation_rule_evaluation(rules, blockers)

    assert blockers == {"required-wave": "该角色已被锁定在其他波次"}
    assert evaluation[0]["status"] == "BLOCKED"
    assert evaluation[0]["reason"] == "该角色已被锁定在其他波次"
    assert evaluation[1]["status"] == "NOT_APPLICABLE"


def test_deepseek_provider_requests_json_and_validates_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        content = json.dumps(
            {
                "schemaVersion": 1,
                "rules": [
                    {
                        "candidateId": "R1",
                        "type": "PLAYER_PREFER_CONTIGUOUS",
                        "enforcement": "SOFT",
                        "playerReference": {"text": "韩亚"},
                        "explanation": "韩亚尽量连续上号",
                    }
                ],
                "unsupportedItems": [],
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "id": "response-1",
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"content": content}}],
            },
        )

    client = httpx.Client(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handler)
    )
    provider = DeepSeekRuleProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=1,
        client=client,
    )

    result = provider.interpret("韩亚尽量连续上号", _context())

    assert result.response_id == "response-1"
    assert result.output.rules[0].candidate_id == "R1"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["thinking"] == {"type": "disabled"}
    user_content = json.loads(captured["messages"][1]["content"])
    assert user_content["context"]["participants"][0] == {
        "playerName": "韩亚",
        "characterName": "剑魂",
        "profession": "剑魂",
        "roleType": "DAMAGE",
        "isTreasureDamage": False,
        "isGroupHunt": False,
    }
    assert "participantId" not in json.dumps(user_content)
    assert "playerId" not in json.dumps(user_content)


def test_deepseek_provider_retries_a_transient_failure_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "schemaVersion": 1,
                                    "rules": [],
                                    "unsupportedItems": [],
                                }
                            )
                        }
                    }
                ],
            },
        )

    client = httpx.Client(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handler)
    )
    provider = DeepSeekRuleProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=1,
        client=client,
    )

    provider.interpret("没有额外要求", _context())

    assert attempts == 2


def test_deepseek_provider_rejects_invalid_or_oversized_responses() -> None:
    def invalid_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    invalid_client = httpx.Client(
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(invalid_handler),
    )
    invalid_provider = DeepSeekRuleProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=1,
        client=invalid_client,
    )

    with pytest.raises(RuleProviderError, match="模型响应不符合规则格式"):
        invalid_provider.interpret("测试", _context())

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "{}"}}]},
        )

    oversized_client = httpx.Client(
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(oversized_handler),
    )
    oversized_provider = DeepSeekRuleProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=1,
        max_response_bytes=10,
        client=oversized_client,
    )

    with pytest.raises(RuleProviderError, match="模型响应超过安全限制"):
        oversized_provider.interpret("测试", _context())
