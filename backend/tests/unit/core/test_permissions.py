from app.core.permissions import (
    ALL_PERMISSION_CODES,
    EDITOR_PERMISSION_CODES,
    PERMISSIONS,
    VIEWER_PERMISSION_CODES,
)


def test_permission_catalog_has_unique_codes_and_modules() -> None:
    codes = [permission.code for permission in PERMISSIONS]
    assert len(codes) == len(set(codes))
    assert set(codes) == ALL_PERMISSION_CODES
    assert all(permission.module and permission.name for permission in PERMISSIONS)


def test_builtin_permission_sets_preserve_existing_access_levels() -> None:
    assert EDITOR_PERMISSION_CODES < ALL_PERMISSION_CODES
    assert VIEWER_PERMISSION_CODES < EDITOR_PERMISSION_CODES
    assert {
        "DUNGEON_READ",
        "ROSTER_READ",
        "SCHEDULE_READ",
        "SCHEDULE_EXPORT",
    } == VIEWER_PERMISSION_CODES
    assert "SCHEDULE_WRITE" in EDITOR_PERMISSION_CODES
    assert "USER_WRITE" not in EDITOR_PERMISSION_CODES
