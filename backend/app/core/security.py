import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("密码至少需要 10 个字符")
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_edit_lock_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_csrf_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_edit_lock_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def utc_now() -> datetime:
    return datetime.now(UTC)


def session_expiry(hours: int) -> datetime:
    return utc_now() + timedelta(hours=hours)
