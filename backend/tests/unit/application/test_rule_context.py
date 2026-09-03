from types import SimpleNamespace

from app.application.schedule_rules import (
    active_rule_set_context_is_current,
    build_rule_context,
)
from app.domain.schedule.rules import rule_context_hash


def test_build_rule_context_snapshots_availability_and_fixed_team_constraints() -> None:
    player_id = "player-1"
    schedule = SimpleNamespace(
        id="schedule-1",
        revision=7,
        wave_count=12,
        preferences=[
            SimpleNamespace(
                player_id=player_id,
                allowed_waves=[2, 1],
                max_wave_count=1,
            )
        ],
        participants=[
            SimpleNamespace(
                id="participant-1",
                player_id_snapshot=player_id,
                player_name_snapshot="韩亚",
                character_name_snapshot="奶爸",
                profession_snapshot="奶爸",
                role_type_snapshot="BUFFER",
                is_treasure_snapshot=False,
                is_fixed_lead_team_buffer_snapshot=True,
                is_group_hunt_snapshot=False,
                is_selected=True,
            )
        ],
        waves=[
            SimpleNamespace(
                wave_no=1,
                teams=[
                    SimpleNamespace(
                        team_key="YELLOW",
                        display_name_snapshot="黄队",
                        display_order_snapshot=2,
                        strength_rank_snapshot=2,
                    ),
                    SimpleNamespace(
                        team_key="RED",
                        display_name_snapshot="红队",
                        display_order_snapshot=1,
                        strength_rank_snapshot=1,
                    ),
                ],
            )
        ],
    )

    context = build_rule_context(schedule)

    assert [team.team_key for team in context.teams] == ["RED", "YELLOW"]
    assert context.participants[0].allowed_waves == (1, 2)
    assert context.participants[0].max_wave_count == 1
    assert context.participants[0].allowed_team_keys == ("RED",)


def test_active_rule_set_context_detects_constraint_changes() -> None:
    schedule = _schedule_fixture()
    schedule.active_rule_set = SimpleNamespace(
        context_hash=rule_context_hash(build_rule_context(schedule))
    )

    assert active_rule_set_context_is_current(schedule)

    schedule.preferences[0].allowed_waves = [3]

    assert not active_rule_set_context_is_current(schedule)


def _schedule_fixture() -> SimpleNamespace:
    player_id = "player-1"
    return SimpleNamespace(
        id="schedule-1",
        revision=7,
        wave_count=12,
        preferences=[
            SimpleNamespace(
                player_id=player_id,
                allowed_waves=[1, 2],
                max_wave_count=1,
            )
        ],
        participants=[
            SimpleNamespace(
                id="participant-1",
                player_id_snapshot=player_id,
                player_name_snapshot="韩亚",
                character_name_snapshot="奶爸",
                profession_snapshot="奶爸",
                role_type_snapshot="BUFFER",
                is_treasure_snapshot=False,
                is_fixed_lead_team_buffer_snapshot=False,
                is_group_hunt_snapshot=False,
                is_selected=True,
            )
        ],
        waves=[
            SimpleNamespace(
                wave_no=1,
                teams=[
                    SimpleNamespace(
                        team_key="RED",
                        display_name_snapshot="红队",
                        display_order_snapshot=1,
                        strength_rank_snapshot=1,
                    )
                ],
            )
        ],
    )
