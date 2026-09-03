import uuid
from types import SimpleNamespace

from app.api.v1.routes import schedules as schedule_routes
from app.schemas.schedule import SchedulePreferencesUpdate


class _FakeDb:
    def commit(self) -> None:
        pass


def _schedule() -> SimpleNamespace:
    player_id = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        revision=3,
        wave_count=12,
        participants=[SimpleNamespace(player_id_snapshot=player_id)],
        preferences=[
            SimpleNamespace(
                player_id=player_id,
                allowed_waves=None,
                max_wave_count=None,
                prefer_early=False,
                prefer_contiguous=False,
            )
        ],
        active_rule_set=SimpleNamespace(status="CONFIRMED"),
        active_rule_set_id=uuid.uuid4(),
        status="DRAFT",
        validation_summary=None,
    )


def _update(
    monkeypatch,
    schedule: SimpleNamespace,
    *,
    allowed_waves: list[int] | None,
    max_wave_count: int | None,
    prefer_early: bool = False,
) -> None:
    monkeypatch.setattr(schedule_routes, "_load", lambda *_args, **_kwargs: schedule)
    monkeypatch.setattr(
        schedule_routes,
        "_claim_revision",
        lambda *_args, **_kwargs: None,
    )
    payload = SchedulePreferencesUpdate.model_validate(
        {
            "baseRevision": schedule.revision,
            "preferences": [
                {
                    "playerId": str(schedule.preferences[0].player_id),
                    "allowedWaves": allowed_waves,
                    "maxWaveCount": max_wave_count,
                    "preferEarly": prefer_early,
                    "preferContiguous": False,
                }
            ],
        }
    )

    schedule_routes.update_schedule_preferences(
        schedule.id,
        payload,
        _FakeDb(),
        SimpleNamespace(id=uuid.uuid4()),
    )


def test_availability_change_invalidates_confirmed_rule_set(monkeypatch) -> None:
    schedule = _schedule()

    _update(monkeypatch, schedule, allowed_waves=[1, 2], max_wave_count=1)

    assert schedule.active_rule_set.status == "STALE"
    assert schedule.active_rule_set_id is None


def test_soft_preference_change_keeps_confirmed_rule_set(monkeypatch) -> None:
    schedule = _schedule()
    active_rule_set_id = schedule.active_rule_set_id

    _update(
        monkeypatch,
        schedule,
        allowed_waves=None,
        max_wave_count=None,
        prefer_early=True,
    )

    assert schedule.active_rule_set.status == "CONFIRMED"
    assert schedule.active_rule_set_id == active_rule_set_id
