import http.cookiejar
import json
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


user = request("/auth/login", "POST", {"username": "admin", "password": "change-me-now"})
assert isinstance(user, dict) and user["role"] == "OWNER"
dungeons = request("/dungeons")
assert isinstance(dungeons, dict) and dungeons["total"] == 1
dungeon = dungeons["items"][0]
source_version = dungeon["versions"][0]
schedule = request(
    "/schedules",
    "POST",
    {"name": "阶段2全栈验收", "dungeonVersionId": source_version["id"]},
)
assert isinstance(schedule, dict) and len(schedule["waves"]) == 12
assert all(len(wave["teams"]) == 3 for wave in schedule["waves"])
assert sum(len(team["slots"]) for team in schedule["waves"][0]["teams"]) == 12
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
draft = request(f"/dungeons/{dungeon['id']}/versions", "POST", version_payload)
assert isinstance(draft, dict) and draft["status"] == "DRAFT"
published = request(f"/dungeon-versions/{draft['id']}/publish", "POST")
assert isinstance(published, dict) and published["status"] == "PUBLISHED"
player = request("/players", "POST", {"displayName": "全栈验收玩家", "characters": []})
assert isinstance(player, dict) and player["displayName"] == "全栈验收玩家"
players = request("/players?search=%E5%85%A8%E6%A0%88")
assert isinstance(players, dict) and players["total"] == 1
request("/auth/logout", "POST")
print("stage 2 schedule foundation smoke passed")
