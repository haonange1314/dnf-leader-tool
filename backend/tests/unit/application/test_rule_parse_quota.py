import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.application.schedule_rules import consume_rule_parse_quota
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.models.identity import NaturalLanguageRateLimit


def test_rule_parse_quota_blocks_requests_after_the_user_limit() -> None:
    now = utc_now()
    user_id = uuid.uuid4()
    row = NaturalLanguageRateLimit(
        user_id=user_id,
        request_count=2,
        window_started_at=now - timedelta(seconds=5),
        updated_at=now,
    )
    db = MagicMock()
    db.scalar.return_value = row
    settings = Settings(
        _env_file=None,
        natural_language_rule_rate_limit_requests=2,
        natural_language_rule_rate_limit_window_seconds=60,
    )

    with pytest.raises(AppError) as error:
        consume_rule_parse_quota(db, user_id, settings)

    assert error.value.status_code == 429
    assert error.value.code == "RULE_PARSE_RATE_LIMITED"
    assert error.value.details["retryAfterSeconds"] > 0


def test_rule_parse_quota_resets_an_expired_window() -> None:
    now = utc_now()
    user_id = uuid.uuid4()
    row = NaturalLanguageRateLimit(
        user_id=user_id,
        request_count=10,
        window_started_at=now - timedelta(seconds=61),
        updated_at=now - timedelta(seconds=61),
    )
    db = MagicMock()
    db.scalar.return_value = row
    settings = Settings(_env_file=None, natural_language_rule_rate_limit_window_seconds=60)

    consume_rule_parse_quota(db, user_id, settings)

    assert row.request_count == 1
    assert row.window_started_at > now - timedelta(seconds=2)
