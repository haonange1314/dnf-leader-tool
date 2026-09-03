import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier

import psycopg
from openpyxl import Workbook

BASE_URL = "http://127.0.0.1:8000/api/v1"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
schedule_lock_tokens: dict[tuple[int, str], str] = {}


def client_request(
    client: urllib.request.OpenerDirector,
    cookies: http.cookiejar.CookieJar,
    path: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if method not in {"GET", "HEAD", "OPTIONS"} and path != "/auth/login":
        csrf_cookie = next((cookie.value for cookie in cookies if cookie.name == "dnf_csrf"), None)
        if csrf_cookie:
            headers["X-CSRF-Token"] = csrf_cookie
        schedule_match = re.match(r"^/schedules/([^/]+)", path)
        edit_lock_token = (
            schedule_lock_tokens.get((id(client), schedule_match.group(1)))
            if schedule_match
            else None
        )
        if edit_lock_token:
            headers["X-Edit-Lock-Token"] = edit_lock_token
    response = client.open(
        urllib.request.Request(
            f"{BASE_URL}{path}",
            data=data,
            method=method,
            headers=headers,
        )
    )
    return json.loads(response.read()) if response.status != 204 else None


def request(path: str, method: str = "GET", payload: dict[str, object] | None = None) -> object:
    return client_request(opener, jar, path, method, payload)


def upload_xlsx(path: str, filename: str, content: bytes) -> object:
    boundary = f"----dnf-smoke-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n"
        "\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    csrf_cookie = next((cookie.value for cookie in jar if cookie.name == "dnf_csrf"), None)
    assert csrf_cookie is not None
    response = opener.open(
        urllib.request.Request(
            f"{BASE_URL}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf_cookie,
            },
        )
    )
    return json.loads(response.read())


def request_error(
    path: str,
    method: str,
    payload: dict[str, object],
    expected_status: int = 422,
) -> dict[str, object]:
    return client_request_error(opener, jar, path, method, payload, expected_status)


def client_request_error(
    client: urllib.request.OpenerDirector,
    cookies: http.cookiejar.CookieJar,
    path: str,
    method: str,
    payload: dict[str, object],
    expected_status: int,
) -> dict[str, object]:
    try:
        client_request(client, cookies, path, method, payload)
    except urllib.error.HTTPError as exc:
        assert exc.code == expected_status
        result = json.loads(exc.read())
        assert isinstance(result, dict)
        return result
    raise AssertionError(f"expected HTTP {expected_status}: {method} {path}")


def acquire_schedule_lock(
    client: urllib.request.OpenerDirector,
    cookies: http.cookiejar.CookieJar,
    schedule_id: str,
) -> dict[str, object]:
    result = client_request(client, cookies, f"/schedules/{schedule_id}/lock", "POST")
    assert isinstance(result, dict) and result["ownedByCurrentUser"] is True
    token = result.get("token")
    assert isinstance(token, str) and token
    schedule_lock_tokens[(id(client), schedule_id)] = token
    return result


limited_jar = http.cookiejar.CookieJar()
limited_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(limited_jar))
for _ in range(5):
    invalid_login = client_request_error(
        limited_opener,
        limited_jar,
        "/auth/login",
        "POST",
        {"username": "rate-limit-smoke", "password": "wrong-password"},
        401,
    )
    assert invalid_login["error"]["code"] == "INVALID_CREDENTIALS"
rate_limited = client_request_error(
    limited_opener,
    limited_jar,
    "/auth/login",
    "POST",
    {"username": "rate-limit-smoke", "password": "wrong-password"},
    429,
)
assert rate_limited["error"]["code"] == "LOGIN_RATE_LIMITED"

user = request("/auth/login", "POST", {"username": "admin", "password": "change-me-now"})
assert isinstance(user, dict) and user["role"] == "OWNER"
assert any(cookie.name == "dnf_csrf" for cookie in jar)
viewer = request(
    "/users",
    "POST",
    {"username": "viewer-smoke", "password": "viewer-password", "role": "VIEWER"},
)
assert isinstance(viewer, dict) and viewer["role"] == "VIEWER"
viewer_jar = http.cookiejar.CookieJar()
viewer_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(viewer_jar))
viewer_login = client_request(
    viewer_opener,
    viewer_jar,
    "/auth/login",
    "POST",
    {"username": "viewer-smoke", "password": "viewer-password"},
)
assert isinstance(viewer_login, dict) and viewer_login["role"] == "VIEWER"
editor = request(
    "/users",
    "POST",
    {"username": "editor-smoke", "password": "editor-password", "role": "EDITOR"},
)
assert isinstance(editor, dict) and editor["role"] == "EDITOR"
editor_jar = http.cookiejar.CookieJar()
editor_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(editor_jar))
editor_login = client_request(
    editor_opener,
    editor_jar,
    "/auth/login",
    "POST",
    {"username": "editor-smoke", "password": "editor-password"},
)
assert isinstance(editor_login, dict) and editor_login["role"] == "EDITOR"
permissions = request("/permissions")
assert isinstance(permissions, dict) and permissions["total"] >= 17
roles = request("/roles")
assert isinstance(roles, dict) and {item["code"] for item in roles["items"]} >= {
    "OWNER",
    "EDITOR",
    "VIEWER",
}
roster_reader_role = request(
    "/roles",
    "POST",
    {
        "code": "ROSTER_READER_SMOKE",
        "name": "人员只读验收",
        "permissionCodes": ["ROSTER_READ"],
    },
)
assert isinstance(roster_reader_role, dict)
assert roster_reader_role["permissionCodes"] == ["ROSTER_READ"]
roster_reader = request(
    "/users",
    "POST",
    {
        "username": "roster-reader-smoke",
        "password": "roster-reader-password",
        "roleId": roster_reader_role["id"],
    },
)
assert isinstance(roster_reader, dict) and roster_reader["role"] == "ROSTER_READER_SMOKE"
roster_reader_jar = http.cookiejar.CookieJar()
roster_reader_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(roster_reader_jar)
)
roster_reader_login = client_request(
    roster_reader_opener,
    roster_reader_jar,
    "/auth/login",
    "POST",
    {"username": "roster-reader-smoke", "password": "roster-reader-password"},
)
assert roster_reader_login["permissions"] == ["ROSTER_READ"]
assert isinstance(client_request(roster_reader_opener, roster_reader_jar, "/players"), dict)
roster_reader_write = client_request_error(
    roster_reader_opener,
    roster_reader_jar,
    "/players",
    "POST",
    {"displayName": "RBAC 不应创建"},
    403,
)
assert roster_reader_write["error"]["code"] == "PERMISSION_DENIED"
assert roster_reader_write["error"]["details"] == {"requiredPermission": "ROSTER_WRITE"}
assert isinstance(client_request(viewer_opener, viewer_jar, "/dungeons"), dict)
try:
    client_request(
        viewer_opener,
        viewer_jar,
        "/players",
        "POST",
        {"displayName": "viewer 不应创建"},
    )
except urllib.error.HTTPError as exc:
    assert exc.code == 403
    assert json.loads(exc.read())["error"]["code"] == "PERMISSION_DENIED"
else:
    raise AssertionError("viewer write must be denied")

try:
    opener.open(
        urllib.request.Request(
            f"{BASE_URL}/players",
            data=json.dumps({"displayName": "缺少 CSRF"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    )
except urllib.error.HTTPError as exc:
    assert exc.code == 403
    assert json.loads(exc.read())["error"]["code"] == "CSRF_INVALID"
else:
    raise AssertionError("unsafe request without CSRF must be denied")

dungeons = request("/dungeons")
assert isinstance(dungeons, dict) and dungeons["total"] == 1
dungeon = dungeons["items"][0]
source_version = dungeon["versions"][0]
blank_name = request_error(
    "/schedules",
    "POST",
    {"name": "   ", "dungeonVersionId": source_version["id"]},
)
assert "detail" in blank_name
inactive_dungeon = request(
    f"/dungeons/{dungeon['id']}",
    "PATCH",
    {
        "name": dungeon["name"],
        "description": dungeon["description"],
        "isActive": False,
    },
)
assert isinstance(inactive_dungeon, dict) and inactive_dungeon["isActive"] is False
inactive_error = request_error(
    "/schedules",
    "POST",
    {"name": "不可创建", "dungeonVersionId": source_version["id"]},
)
assert inactive_error["error"]["code"] == "DUNGEON_INACTIVE"
request(
    f"/dungeons/{dungeon['id']}",
    "PATCH",
    {
        "name": dungeon["name"],
        "description": dungeon["description"],
        "isActive": True,
    },
)
inactive_player = request(
    "/players",
    "POST",
    {
        "displayName": "已停用验收玩家",
        "isActive": False,
        "characters": [
            {
                "profession": "测试职业",
                "roleType": "DAMAGE",
                "damageScore": 100,
                "isTreasureDamage": False,
                "defaultRaidParticipant": True,
                "isActive": True,
            }
        ],
    },
)
assert isinstance(inactive_player, dict)
workflow_player = request(
    "/players",
    "POST",
    {
        "displayName": "排表工作流玩家",
        "characters": [
            {
                "profession": "测试职业",
                "roleType": "DAMAGE",
                "damageScore": 500,
                "isTreasureDamage": True,
                "defaultRaidParticipant": True,
                "isActive": True,
            },
            {
                "profession": "测试奶系",
                "roleType": "BUFFER",
                "bufferScore": 50,
                "defaultRaidParticipant": True,
                "isActive": True,
            },
        ],
    },
)
assert isinstance(workflow_player, dict)
players_before_reorder = request("/players")
assert isinstance(players_before_reorder, dict)
reordered_player_ids = [
    item["id"] for item in reversed(players_before_reorder["items"])
]
player_reorder = request(
    "/players/reorder",
    "PUT",
    {"orderedIds": reordered_player_ids},
)
assert isinstance(player_reorder, dict) and player_reorder["updated"] == 2
players_after_reorder = request("/players")
assert isinstance(players_after_reorder, dict)
assert [item["id"] for item in players_after_reorder["items"]] == reordered_player_ids
partial_reorder = request_error(
    "/players/reorder",
    "PUT",
    {"orderedIds": reordered_player_ids[:1]},
    409,
)
assert partial_reorder["error"]["code"] == "PERSONNEL_ORDER_CHANGED"

reordered_character_ids = [
    item["id"] for item in reversed(workflow_player["characters"])
]
character_reorder = request(
    f"/players/{workflow_player['id']}/characters/reorder",
    "PUT",
    {"orderedIds": reordered_character_ids},
)
assert isinstance(character_reorder, dict) and character_reorder["updated"] == 2
workflow_player_after_reorder = request(f"/players/{workflow_player['id']}")
assert isinstance(workflow_player_after_reorder, dict)
assert [
    item["id"] for item in workflow_player_after_reorder["characters"]
] == reordered_character_ids
duplicate_profession = request_error(
    f"/players/{workflow_player['id']}/characters",
    "POST",
    {
        "profession": "测试职业",
        "roleType": "DAMAGE",
        "damageScore": 450,
        "isTreasureDamage": False,
        "defaultRaidParticipant": True,
        "isActive": True,
    },
    409,
)
assert duplicate_profession["error"]["code"] == "PERSONNEL_DUPLICATE"

workbook = Workbook()
sheet = workbook.active
assert sheet is not None
sheet.title = "角色数据"
sheet.append(
    (
        "序号",
        "玩家昵称",
        "职业",
        "类型",
        "模拟伤害亿/增益量万",
        "是否秘宝C",
        "固定红队奶",
        "是否群猎",
        "是否参与团本",
    )
)
sheet.append((1, "已停用验收玩家", "测试职业", "C", "100.00", "否", "否", "否", "是"))
sheet.append((2, "排表工作流玩家", "测试职业", "C", "500.00", "是", "否", "否", "是"))
sheet.append((3, "排表工作流玩家", "测试奶系", "奶", "50.00", "否", "否", "否", "是"))
workbook_stream = BytesIO()
workbook.save(workbook_stream)
import_preview = upload_xlsx(
    "/imports/characters/preview",
    "人员排序验收.xlsx",
    workbook_stream.getvalue(),
)
assert isinstance(import_preview, dict)
assert import_preview["summary"] == {"create": 0, "update": 0, "ignore": 3, "error": 0}
import_commit = request(
    f"/imports/characters/{import_preview['id']}/commit",
    "POST",
)
assert isinstance(import_commit, dict) and import_commit["status"] == "COMMITTED"
players_after_import = request("/players")
assert isinstance(players_after_import, dict)
assert [item["id"] for item in players_after_import["items"][:2]] == [
    inactive_player["id"],
    workflow_player["id"],
]
workflow_player_after_import = request(f"/players/{workflow_player['id']}")
assert isinstance(workflow_player_after_import, dict)
assert [
    item["profession"] for item in workflow_player_after_import["characters"]
] == ["测试职业", "测试奶系"]

lifecycle_schedule = request(
    "/schedules",
    "POST",
    {"name": "排表生命周期验收", "dungeonVersionId": source_version["id"]},
)
assert isinstance(lifecycle_schedule, dict) and lifecycle_schedule["revision"] == 1
editor_delete_denied = client_request_error(
    editor_opener,
    editor_jar,
    f"/schedules/{lifecycle_schedule['id']}",
    "DELETE",
    {"baseRevision": 1, "confirmationName": lifecycle_schedule["name"]},
    403,
)
assert editor_delete_denied["error"]["details"] == {
    "requiredPermission": "SCHEDULE_DELETE"
}
acquire_schedule_lock(opener, jar, lifecycle_schedule["id"])
archived_schedule = request(
    f"/schedules/{lifecycle_schedule['id']}/archive",
    "POST",
    {"baseRevision": 1},
)
assert isinstance(archived_schedule, dict)
assert archived_schedule["status"] == "ARCHIVED" and archived_schedule["revision"] == 2
archived_validation = request(
    f"/schedules/{lifecycle_schedule['id']}/validate",
    "POST",
    {"baseRevision": 2},
)
assert isinstance(archived_validation, dict) and archived_validation["revision"] == 2
archived_after_validation = request(f"/schedules/{lifecycle_schedule['id']}")
assert isinstance(archived_after_validation, dict)
assert archived_after_validation["validationSummary"] is None
active_schedules = request("/schedules")
assert isinstance(active_schedules, dict)
assert lifecycle_schedule["id"] not in {item["id"] for item in active_schedules["items"]}
all_schedules = request("/schedules?includeArchived=true")
assert isinstance(all_schedules, dict)
assert lifecycle_schedule["id"] in {item["id"] for item in all_schedules["items"]}
restored_lifecycle_schedule = request(
    f"/schedules/{lifecycle_schedule['id']}/restore",
    "POST",
    {"baseRevision": 2},
)
assert isinstance(restored_lifecycle_schedule, dict)
assert restored_lifecycle_schedule["status"] == "DRAFT"
assert restored_lifecycle_schedule["revision"] == 3
delete_name_mismatch = request_error(
    f"/schedules/{lifecycle_schedule['id']}",
    "DELETE",
    {"baseRevision": 3, "confirmationName": "错误名称"},
)
assert delete_name_mismatch["error"]["code"] == "SCHEDULE_DELETE_CONFIRMATION_MISMATCH"
assert request(
    f"/schedules/{lifecycle_schedule['id']}",
    "DELETE",
    {"baseRevision": 3, "confirmationName": lifecycle_schedule["name"]},
) is None
schedule_lock_tokens.pop((id(opener), lifecycle_schedule["id"]), None)
after_delete = request("/schedules?includeArchived=true")
assert isinstance(after_delete, dict)
assert lifecycle_schedule["id"] not in {item["id"] for item in after_delete["items"]}

schedule = request(
    "/schedules",
    "POST",
    {"name": "阶段2全栈验收", "dungeonVersionId": source_version["id"]},
)
assert isinstance(schedule, dict) and len(schedule["waves"]) == 12
missing_lock = request_error(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 1, "waveCount": 2},
    expected_status=423,
)
assert missing_lock["error"]["code"] == "EDIT_LOCK_TOKEN_REQUIRED"
acquire_schedule_lock(opener, jar, schedule["id"])
viewer_validation = client_request(
    viewer_opener,
    viewer_jar,
    f"/schedules/{schedule['id']}/validate",
    "POST",
    {"baseRevision": 1},
)
assert isinstance(viewer_validation, dict) and viewer_validation["revision"] == 1
viewer_schedule = client_request(
    viewer_opener,
    viewer_jar,
    f"/schedules/{schedule['id']}",
)
assert isinstance(viewer_schedule, dict) and viewer_schedule["validationSummary"] is None
second_owner_jar = http.cookiejar.CookieJar()
second_owner_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(second_owner_jar)
)
second_owner = client_request(
    second_owner_opener,
    second_owner_jar,
    "/auth/login",
    "POST",
    {"username": "admin", "password": "change-me-now"},
)
assert isinstance(second_owner, dict) and second_owner["role"] == "OWNER"
lock_conflict = client_request_error(
    second_owner_opener,
    second_owner_jar,
    f"/schedules/{schedule['id']}/lock",
    "POST",
    {},
    423,
)
assert lock_conflict["error"]["code"] == "EDIT_LOCKED"
heartbeat = request(f"/schedules/{schedule['id']}/lock/heartbeat", "POST")
assert isinstance(heartbeat, dict) and heartbeat["ownedByCurrentUser"] is True
database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
with psycopg.connect(database_url) as lock_db:
    result = lock_db.execute(
        "UPDATE edit_locks SET expires_at = now() - interval '1 second' WHERE schedule_id = %s",
        (schedule["id"],),
    )
    assert result.rowcount == 1
takeover = client_request(
    second_owner_opener,
    second_owner_jar,
    f"/schedules/{schedule['id']}/lock/takeover",
    "POST",
)
assert isinstance(takeover, dict) and takeover["ownedByCurrentUser"] is True
second_token = takeover.get("token")
assert isinstance(second_token, str) and second_token
schedule_lock_tokens[(id(second_owner_opener), schedule["id"])] = second_token
stale_lock = request_error(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 1, "waveCount": 2},
    expected_status=423,
)
assert stale_lock["error"]["code"] == "EDIT_LOCK_INVALID"
client_request(
    second_owner_opener,
    second_owner_jar,
    f"/schedules/{schedule['id']}/lock",
    "DELETE",
)
schedule_lock_tokens.pop((id(second_owner_opener), schedule["id"]), None)
schedule_lock_tokens.pop((id(opener), schedule["id"]), None)
acquire_schedule_lock(opener, jar, schedule["id"])
assert all(len(wave["teams"]) == 3 for wave in schedule["waves"])
assert sum(len(team["slots"]) for team in schedule["waves"][0]["teams"]) == 12
assert all(
    participant["playerIdSnapshot"] != inactive_player["id"]
    for participant in schedule["participants"]
)
assert len(schedule["participants"]) == 2
report = request(f"/schedules/{schedule['id']}/validate", "POST", {"baseRevision": 1})
assert isinstance(report, dict) and report["revision"] == 1
schedule = request(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 1, "waveCount": 2},
)
assert isinstance(schedule, dict) and schedule["revision"] == 2
assert len(schedule["waves"]) == 2
schedule = request(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 2, "waveCount": 3},
)
assert isinstance(schedule, dict) and schedule["revision"] == 3
assert len(schedule["waves"]) == 3
participant_ids = [participant["id"] for participant in schedule["participants"]]
schedule = request(
    f"/schedules/{schedule['id']}/participants",
    "PUT",
    {"baseRevision": 3, "selectedParticipantIds": participant_ids},
)
assert isinstance(schedule, dict) and schedule["revision"] == 4
schedule = request(
    f"/schedules/{schedule['id']}/player-preferences",
    "PUT",
    {
        "baseRevision": 4,
        "preferences": [
            {
                "playerId": workflow_player["id"],
                "allowedWaves": [1, 3],
                "maxWaveCount": 3,
                "preferEarly": True,
                "preferContiguous": True,
            }
        ],
    },
)
assert isinstance(schedule, dict) and schedule["revision"] == 5
schedule = request(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 5, "waveCount": 2},
)
assert isinstance(schedule, dict) and schedule["revision"] == 6
assert schedule["preferences"][0]["allowedWaves"] == [1]
assert schedule["preferences"][0]["maxWaveCount"] == 2
new_character = request(
    f"/players/{workflow_player['id']}/characters",
    "POST",
    {
        "profession": "测试职业二",
        "roleType": "DAMAGE",
        "damageScore": 450,
        "isTreasureDamage": False,
        "defaultRaidParticipant": True,
        "isActive": True,
    },
)
assert isinstance(new_character, dict)
sync_preview = request(f"/schedules/{schedule['id']}/sync-characters/preview", "POST")
assert isinstance(sync_preview, dict) and sync_preview["summary"]["ADD"] == 1
schedule = request(
    f"/schedules/{schedule['id']}/sync-characters/commit",
    "POST",
    {
        "baseRevision": 6,
        "sourceFingerprint": sync_preview["sourceFingerprint"],
    },
)
assert isinstance(schedule, dict) and schedule["revision"] == 7
assert len(schedule["participants"]) == 3
workflow_report = request(f"/schedules/{schedule['id']}/validate", "POST", {"baseRevision": 7})
assert isinstance(workflow_report, dict)
workflow_issue_codes = {issue["code"] for issue in workflow_report["issues"]}
assert "PLAYER_WAVE_CAPACITY_INSUFFICIENT" in workflow_issue_codes
assert "DISTINCT_PLAYER_SHORTAGE" in workflow_issue_codes
stale_validation = request_error(
    f"/schedules/{schedule['id']}/validate",
    "POST",
    {"baseRevision": 6},
    expected_status=409,
)
assert stale_validation["error"]["code"] == "SCHEDULE_REVISION_CONFLICT"
copy_preview = request(
    f"/schedules/{schedule['id']}/copy/preview",
    "POST",
    {
        "baseRevision": 7,
        "targetDungeonVersionId": source_version["id"],
        "waveCount": 2,
    },
)
assert isinstance(copy_preview, dict) and copy_preview["changes"] == []
copied_schedule = request(
    f"/schedules/{schedule['id']}/copy",
    "POST",
    {
        "baseRevision": 7,
        "name": "阶段2复制验收",
        "targetDungeonVersionId": source_version["id"],
        "waveCount": 2,
        "migrationFingerprint": copy_preview["migrationFingerprint"],
    },
)
assert isinstance(copied_schedule, dict)
acquire_schedule_lock(opener, jar, copied_schedule["id"])
assert copied_schedule["revision"] == 1 and copied_schedule["status"] == "DRAFT"
assert copied_schedule["waveCount"] == 2 and len(copied_schedule["waves"]) == 2
assert len(copied_schedule["participants"]) == 3
assert copied_schedule["preferences"][0]["allowedWaves"] == [1]
assert all(
    slot["participantId"] is None and slot["isLocked"] is False
    for wave in copied_schedule["waves"]
    for team in wave["teams"]
    for slot in team["slots"]
)
generation = request(
    f"/schedules/{copied_schedule['id']}/generate",
    "POST",
    {
        "baseRevision": 1,
        "preserveLocks": True,
        "randomSeed": 42,
        "timeLimitSeconds": 2,
    },
)
assert isinstance(generation, dict)
assert generation["run"]["status"] == "PARTIAL"
assert generation["run"]["resultRevision"] == 2
generated_schedule = generation["schedule"]
assert generated_schedule["revision"] == 2
assert (
    sum(
        slot["participantId"] is not None
        for wave in generated_schedule["waves"]
        for team in wave["teams"]
        for slot in team["slots"]
    )
    == 1
)
assert (
    sum(
        participant["unassignedReason"] is not None
        for participant in generated_schedule["participants"]
    )
    == 2
)
regeneration = request(
    f"/schedules/{copied_schedule['id']}/generate",
    "POST",
    {
        "baseRevision": 2,
        "preserveLocks": True,
        "randomSeed": 43,
        "timeLimitSeconds": 2,
    },
)
assert isinstance(regeneration, dict)
assert regeneration["schedule"]["revision"] == 3
runs = request(f"/schedules/{copied_schedule['id']}/generation-runs")
assert isinstance(runs, dict) and runs["total"] == 2
assert runs["items"][0]["id"] == regeneration["run"]["id"]
revision_error = request_error(
    f"/schedules/{schedule['id']}",
    "PATCH",
    {"baseRevision": 1, "name": "过期写入"},
    expected_status=409,
)
assert revision_error["error"]["code"] == "SCHEDULE_REVISION_CONFLICT"
version_payload = {
    "defaultWaveCount": source_version["defaultWaveCount"],
    "minWaveCount": source_version["minWaveCount"],
    "maxWaveCount": source_version["maxWaveCount"],
    "formula": source_version["formula"],
    "teams": [
        {key: value for key, value in team.items() if key != "id"}
        for team in source_version["teams"]
    ],
    "compositionRules": source_version["compositionRules"],
    "specialRoleRules": source_version["specialRoleRules"],
    "strengthOrderRules": source_version["strengthOrderRules"],
    "optimizationRules": source_version["optimizationRules"],
    "missingSlotPolicy": source_version["missingSlotPolicy"],
}
concurrent_dungeon = request(
    "/dungeons",
    "POST",
    {
        "code": "CONCURRENT_VERSION_SMOKE",
        "name": "并发版本验收副本",
        "isActive": True,
    },
)
assert isinstance(concurrent_dungeon, dict)
concurrent_barrier = Barrier(2)


def create_concurrent_version(
    client: urllib.request.OpenerDirector, cookies: http.cookiejar.CookieJar
) -> object:
    concurrent_barrier.wait()
    return client_request(
        client,
        cookies,
        f"/dungeons/{concurrent_dungeon['id']}/versions",
        "POST",
        version_payload,
    )


with ThreadPoolExecutor(max_workers=2) as executor:
    concurrent_futures = [
        executor.submit(create_concurrent_version, opener, jar),
        executor.submit(create_concurrent_version, editor_opener, editor_jar),
    ]
    concurrent_versions = [future.result() for future in concurrent_futures]
assert all(isinstance(version, dict) for version in concurrent_versions)
assert sorted(version["versionNo"] for version in concurrent_versions) == [1, 2]

damage_only_payload = {
    **version_payload,
    "compositionRules": {
        "schemaVersion": 1,
        "allowed": [
            {
                "code": "4D",
                "applicableTeamKeys": ["RED", "YELLOW", "GREEN"],
                "roles": {"DAMAGE": 4},
                "priority": 1,
            }
        ],
    },
    "specialRoleRules": {"schemaVersion": 1, "rules": []},
    "strengthOrderRules": {"schemaVersion": 1, "orders": []},
    "optimizationRules": {"schemaVersion": 1, "balanceAcrossWaves": []},
}
draft = request(f"/dungeons/{dungeon['id']}/versions", "POST", damage_only_payload)
assert isinstance(draft, dict) and draft["status"] == "DRAFT"
published = request(f"/dungeon-versions/{draft['id']}/publish", "POST")
assert isinstance(published, dict) and published["status"] == "PUBLISHED"
immutable_error = request_error(
    f"/dungeon-versions/{published['id']}",
    "PATCH",
    damage_only_payload,
    expected_status=409,
)
assert immutable_error["error"]["code"] == "DUNGEON_VERSION_IMMUTABLE"
migration_preview = request(
    f"/schedules/{schedule['id']}/copy/preview",
    "POST",
    {
        "baseRevision": 7,
        "targetDungeonVersionId": published["id"],
        "waveCount": 2,
    },
)
assert isinstance(migration_preview, dict) and migration_preview["migrationRequired"] is True
assert "COMPOSITION_RULES_CHANGED" in {change["code"] for change in migration_preview["changes"]}
preview_required = request_error(
    f"/schedules/{schedule['id']}/copy",
    "POST",
    {
        "baseRevision": 7,
        "name": "不应创建的迁移副本",
        "targetDungeonVersionId": published["id"],
        "waveCount": 2,
    },
    expected_status=409,
)
assert preview_required["error"]["code"] == "COPY_PREVIEW_REQUIRED"
migrated_schedule = request(
    f"/schedules/{schedule['id']}/copy",
    "POST",
    {
        "baseRevision": 7,
        "name": "阶段2迁移复制验收",
        "targetDungeonVersionId": published["id"],
        "waveCount": 2,
        "migrationFingerprint": migration_preview["migrationFingerprint"],
    },
)
assert isinstance(migrated_schedule, dict)
assert migrated_schedule["dungeonVersionId"] == published["id"]
assert len(migrated_schedule["waves"]) == 2
damage_only_schedule = request(
    "/schedules",
    "POST",
    {"name": "纯 C 规则验收", "dungeonVersionId": published["id"], "waveCount": 1},
)
assert isinstance(damage_only_schedule, dict)
acquire_schedule_lock(opener, jar, damage_only_schedule["id"])
damage_only_report = request(
    f"/schedules/{damage_only_schedule['id']}/validate",
    "POST",
    {"baseRevision": 1},
)
assert isinstance(damage_only_report, dict)
damage_only_issues = {
    issue["code"]: issue["message_params"] for issue in damage_only_report["issues"]
}
assert damage_only_issues["DAMAGE_IDEAL_SHORTAGE"]["required"] == 12
assert "BUFFER_BASE_SHORTAGE" not in damage_only_issues

for index in range(11):
    created_player = request(
        "/players",
        "POST",
        {
            "displayName": f"发布验收玩家 {index + 1}",
            "characters": [
                {
                    "name": f"发布验收 C {index + 1}",
                    "profession": "测试职业",
                    "roleType": "DAMAGE",
                    "damageScore": 400 + index,
                    "isTreasureDamage": False,
                    "defaultRaidParticipant": True,
                    "isActive": True,
                }
            ],
        },
    )
    assert isinstance(created_player, dict)

publishable_schedule = request(
    "/schedules",
    "POST",
    {"name": "阶段4发布验收", "dungeonVersionId": published["id"], "waveCount": 1},
)
assert isinstance(publishable_schedule, dict)
acquire_schedule_lock(opener, jar, publishable_schedule["id"])
damage_participant_ids = []
selected_damage_players = set()
for participant in publishable_schedule["participants"]:
    if (
        participant["roleTypeSnapshot"] == "DAMAGE"
        and participant["playerIdSnapshot"] not in selected_damage_players
    ):
        damage_participant_ids.append(participant["id"])
        selected_damage_players.add(participant["playerIdSnapshot"])
assert len(damage_participant_ids) == 12
publishable_schedule = request(
    f"/schedules/{publishable_schedule['id']}/participants",
    "PUT",
    {"baseRevision": 1, "selectedParticipantIds": damage_participant_ids},
)
assert isinstance(publishable_schedule, dict) and publishable_schedule["revision"] == 2
publishable_generation = request(
    f"/schedules/{publishable_schedule['id']}/generate",
    "POST",
    {
        "baseRevision": 2,
        "preserveLocks": True,
        "randomSeed": 44,
        "timeLimitSeconds": 2,
    },
)
assert isinstance(publishable_generation, dict)
assert publishable_generation["run"]["status"] in {"OPTIMAL", "FEASIBLE", "SUCCEEDED"}
publishable_schedule = publishable_generation["schedule"]
assert publishable_schedule["revision"] == 3
first_slot = publishable_schedule["waves"][0]["teams"][0]["slots"][0]
operation_id = str(uuid.uuid4())
lock_response = request(
    f"/schedules/{publishable_schedule['id']}/commands",
    "POST",
    {
        "operationId": operation_id,
        "baseRevision": 3,
        "operations": [{"type": "LOCK_SLOT", "slotId": first_slot["id"], "locked": True}],
    },
)
assert isinstance(lock_response, dict) and lock_response["revision"] == 4
assert lock_response["inverseOperations"][0]["type"] == "LOCK_SLOT"
assert lock_response["inverseOperations"][0]["slotId"] == first_slot["id"]
assert lock_response["inverseOperations"][0]["locked"] is False
lock_retry = request(
    f"/schedules/{publishable_schedule['id']}/commands",
    "POST",
    {
        "operationId": operation_id,
        "baseRevision": 3,
        "operations": [{"type": "LOCK_SLOT", "slotId": first_slot["id"], "locked": True}],
    },
)
assert lock_retry == lock_response
unlock_response = request(
    f"/schedules/{publishable_schedule['id']}/commands",
    "POST",
    {
        "operationId": str(uuid.uuid4()),
        "baseRevision": 4,
        "operations": lock_response["inverseOperations"],
    },
)
assert isinstance(unlock_response, dict) and unlock_response["revision"] == 5
publication_check = request(
    f"/schedules/{publishable_schedule['id']}/publication-check",
    "POST",
    {"baseRevision": 5},
)
assert isinstance(publication_check, dict)
assert publication_check["publishable"] is True
assert publication_check["summary"]["error"] == 0
draft_text_export = opener.open(
    f"{BASE_URL}/schedules/{publishable_schedule['id']}/exports/text"
)
assert draft_text_export.read().decode().startswith("【草稿】阶段4发布验收")
draft_excel_export = opener.open(
    f"{BASE_URL}/schedules/{publishable_schedule['id']}/exports/excel"
)
assert draft_excel_export.read(2) == b"PK"
draft_image_export = opener.open(
    f"{BASE_URL}/schedules/{publishable_schedule['id']}/exports/image"
)
assert draft_image_export.read(8) == b"\x89PNG\r\n\x1a\n"
published_schedule = request(
    f"/schedules/{publishable_schedule['id']}/publish",
    "POST",
    {"baseRevision": 5, "confirmWarnings": False},
)
assert isinstance(published_schedule, dict)
assert published_schedule["schedule"]["status"] == "PUBLISHED"
assert published_schedule["schedule"]["revision"] == 6
assert published_schedule["version"]["versionNo"] == 1
assert published_schedule["version"]["snapshot"]["schemaVersion"] == 3
assert published_schedule["version"]["snapshot"]["dungeon"]["versionId"] == published["id"]
assert published_schedule["version"]["snapshot"]["formula"]["code"]
assert "issues" in published_schedule["version"]["snapshot"]
schedule_version_id = published_schedule["version"]["id"]
versions = request(f"/schedules/{publishable_schedule['id']}/versions")
assert isinstance(versions, dict) and versions["total"] == 1
share_link = request(
    f"/schedule-versions/{schedule_version_id}/share-links",
    "POST",
    {"expiresInDays": 7},
)
assert isinstance(share_link, dict) and share_link["token"]
share_links = request(f"/schedule-versions/{schedule_version_id}/share-links")
assert isinstance(share_links, dict) and share_links["total"] == 1
assert share_links["items"][0]["status"] == "ACTIVE"
public_version = request(f"/share/{share_link['token']}")
assert isinstance(public_version, dict)
assert public_version["snapshot"]["name"] == "阶段4发布验收"
request(f"/share-links/{share_link['id']}", "DELETE")
revoked_share = request_error(f"/share/{share_link['token']}", "GET", {}, expected_status=404)
assert revoked_share["error"]["code"] == "SHARE_LINK_INVALID"
share_links = request(f"/schedule-versions/{schedule_version_id}/share-links")
assert share_links["items"][0]["status"] == "REVOKED"
text_export = opener.open(f"{BASE_URL}/schedule-versions/{schedule_version_id}/exports/text")
assert "阶段4发布验收" in text_export.read().decode()
excel_export = opener.open(f"{BASE_URL}/schedule-versions/{schedule_version_id}/exports/excel")
assert excel_export.read(2) == b"PK"
image_export = opener.open(f"{BASE_URL}/schedule-versions/{schedule_version_id}/exports/image")
assert image_export.read(8) == b"\x89PNG\r\n\x1a\n"
version_copy = request(
    f"/schedules/{publishable_schedule['id']}/versions/1/copy-as-draft",
    "POST",
    {"name": "阶段4历史版本副本"},
)
assert isinstance(version_copy, dict)
assert version_copy["name"] == "阶段4历史版本副本"
assert version_copy["status"] == "DRAFT" and version_copy["revision"] == 1
assert any(
    slot["participantId"] is not None
    for wave in version_copy["waves"]
    for team in wave["teams"]
    for slot in team["slots"]
)
restored_schedule = request(
    f"/schedules/{publishable_schedule['id']}/versions/1/restore-as-draft",
    "POST",
    {"baseRevision": 6},
)
assert isinstance(restored_schedule, dict)
assert restored_schedule["status"] == "DRAFT" and restored_schedule["revision"] == 7
oversized_payload = {
    **version_payload,
    "defaultWaveCount": 19,
    "minWaveCount": 1,
    "maxWaveCount": 50,
    "teams": [
        {
            "teamKey": "PARTY",
            "displayName": "超大队伍",
            "displayColor": "#3e63dd",
            "displayOrder": 0,
            "memberCount": 64,
            "strengthRank": None,
        }
    ],
    "compositionRules": {
        "schemaVersion": 1,
        "allowed": [
            {
                "code": "64D",
                "applicableTeamKeys": ["PARTY"],
                "roles": {"DAMAGE": 64},
                "priority": 1,
            }
        ],
    },
    "specialRoleRules": {"schemaVersion": 1, "rules": []},
    "strengthOrderRules": {"schemaVersion": 1, "orders": []},
    "optimizationRules": {"schemaVersion": 1, "balanceAcrossWaves": []},
}
oversized_draft = request(f"/dungeons/{dungeon['id']}/versions", "POST", oversized_payload)
assert isinstance(oversized_draft, dict)
oversized_version = request(f"/dungeon-versions/{oversized_draft['id']}/publish", "POST")
assert isinstance(oversized_version, dict)
limit_error = request_error(
    "/schedules",
    "POST",
    {
        "name": "超限排表",
        "dungeonVersionId": oversized_version["id"],
        "waveCount": 19,
    },
)
assert limit_error["error"]["code"] == "SCHEDULE_POSITION_LIMIT_EXCEEDED"
assert limit_error["error"]["details"] == {"limit": 1200, "current": 1216}
player = request("/players", "POST", {"displayName": "全栈验收玩家", "characters": []})
assert isinstance(player, dict) and player["displayName"] == "全栈验收玩家"
players = request("/players?search=%E5%85%A8%E6%A0%88")
assert isinstance(players, dict) and players["total"] == 1
audit_logs = request("/audit-logs?action=AUTH_LOGIN")
assert isinstance(audit_logs, dict) and audit_logs["total"] > 0
assert all(item["action"] == "AUTH_LOGIN" for item in audit_logs["items"])
failed_audit_logs = request("/audit-logs?outcome=FAILURE&limit=10")
assert isinstance(failed_audit_logs, dict)
assert all(item["outcome"] == "FAILURE" for item in failed_audit_logs["items"])
managed_users = request("/users?search=roster-reader")
assert isinstance(managed_users, dict) and managed_users["total"] == 1
assert managed_users["items"][0]["active_session_count"] == 1

updated_admin = request(
    f"/users/{user['id']}",
    "PATCH",
    {"password": "updated-admin-password"},
)
assert isinstance(updated_admin, dict) and updated_admin["id"] == user["id"]
current_session = request("/auth/me")
assert isinstance(current_session, dict) and current_session["id"] == user["id"]
revoked_session = client_request_error(
    second_owner_opener,
    second_owner_jar,
    "/auth/me",
    "GET",
    {},
    401,
)
assert revoked_session["error"]["code"] == "SESSION_INVALID"

source_limit_jar = http.cookiejar.CookieJar()
source_limit_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(source_limit_jar)
)
for index in range(20):
    source_failure = client_request_error(
        source_limit_opener,
        source_limit_jar,
        "/auth/login",
        "POST",
        {"username": f"source-limit-{index}", "password": "wrong-password"},
        401,
    )
    assert source_failure["error"]["code"] == "INVALID_CREDENTIALS"
source_limited = client_request_error(
    source_limit_opener,
    source_limit_jar,
    "/auth/login",
    "POST",
    {"username": "source-limit-final", "password": "wrong-password"},
    429,
)
assert source_limited["error"]["code"] == "LOGIN_RATE_LIMITED"
assert "SOURCE" in source_limited["error"]["details"]["scopes"]
request("/auth/logout", "POST")
print("stage 5 identity, edit lease, publication, export and recovery smoke passed")
