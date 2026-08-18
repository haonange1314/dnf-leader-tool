import http.cookiejar
import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000/api/v1"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(path: str, method: str = "GET", payload: dict[str, object] | None = None) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    response = opener.open(
        urllib.request.Request(
            f"{BASE_URL}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
    )
    return json.loads(response.read()) if response.status != 204 else None


def request_error(
    path: str,
    method: str,
    payload: dict[str, object],
    expected_status: int = 422,
) -> dict[str, object]:
    try:
        request(path, method, payload)
    except urllib.error.HTTPError as exc:
        assert exc.code == expected_status
        result = json.loads(exc.read())
        assert isinstance(result, dict)
        return result
    raise AssertionError(f"expected HTTP {expected_status}: {method} {path}")


user = request("/auth/login", "POST", {"username": "admin", "password": "change-me-now"})
assert isinstance(user, dict) and user["role"] == "OWNER"
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
                "name": "不应进入排表",
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
schedule = request(
    "/schedules",
    "POST",
    {"name": "阶段2全栈验收", "dungeonVersionId": source_version["id"]},
)
assert isinstance(schedule, dict) and len(schedule["waves"]) == 12
assert all(len(wave["teams"]) == 3 for wave in schedule["waves"])
assert sum(len(team["slots"]) for team in schedule["waves"][0]["teams"]) == 12
assert all(
    participant["playerIdSnapshot"] != inactive_player["id"]
    for participant in schedule["participants"]
)
report = request(f"/schedules/{schedule['id']}/validate", "POST")
assert isinstance(report, dict) and report["summary"]["info"] == 1
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
damage_only_schedule = request(
    "/schedules",
    "POST",
    {"name": "纯 C 规则验收", "dungeonVersionId": published["id"], "waveCount": 1},
)
assert isinstance(damage_only_schedule, dict)
damage_only_report = request(f"/schedules/{damage_only_schedule['id']}/validate", "POST")
assert isinstance(damage_only_report, dict)
damage_only_issues = {
    issue["code"]: issue["message_params"] for issue in damage_only_report["issues"]
}
assert damage_only_issues["DAMAGE_IDEAL_SHORTAGE"]["required"] == 12
assert "BUFFER_BASE_SHORTAGE" not in damage_only_issues
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
oversized_draft = request(
    f"/dungeons/{dungeon['id']}/versions", "POST", oversized_payload
)
assert isinstance(oversized_draft, dict)
oversized_version = request(
    f"/dungeon-versions/{oversized_draft['id']}/publish", "POST"
)
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
request("/auth/logout", "POST")
print("stage 2 schedule foundation smoke passed")
