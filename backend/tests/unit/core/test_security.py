from app.core.security import (
    create_csrf_token,
    create_edit_lock_token,
    hash_csrf_token,
    hash_edit_lock_token,
    hash_password,
    hash_session_token,
    normalize_username,
    verify_password,
)


def test_password_hash_and_session_hash() -> None:
    password_hash = hash_password("safe-password-123")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "safe-password-123")
    assert not verify_password(password_hash, "wrong-password")
    assert hash_session_token("token") == hash_session_token("token")


def test_password_rejects_short_value() -> None:
    try:
        hash_password("short")
    except ValueError as exc:
        assert "10" in str(exc)
    else:
        raise AssertionError("short password must be rejected")


def test_csrf_token_is_random_and_hashable() -> None:
    first = create_csrf_token()
    second = create_csrf_token()

    assert first != second
    assert len(first) >= 32
    assert hash_csrf_token(first) == hash_csrf_token(first)
    assert hash_csrf_token(first) != hash_csrf_token(second)


def test_username_is_normalized_for_login_and_uniqueness() -> None:
    assert normalize_username("  Admin  ") == "admin"
    assert normalize_username("ＤＮＦ") == "ｄｎｆ"


def test_edit_lock_tokens_are_random_and_only_compared_by_hash() -> None:
    first = create_edit_lock_token()
    second = create_edit_lock_token()

    assert first != second
    assert hash_edit_lock_token(first) == hash_edit_lock_token(first)
    assert hash_edit_lock_token(first) != hash_edit_lock_token(second)
