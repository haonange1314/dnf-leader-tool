from app.core.security import hash_password, hash_session_token, verify_password


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
