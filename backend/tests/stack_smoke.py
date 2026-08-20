import http.cookiejar
import json
import urllib.error
import urllib.request
import uuid

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
workflow_player = request(
    "/players",
    "POST",
    {
        "displayName": "排表工作流玩家",
        "characters": [
            {
                "name": "工作流主 C",
                "profession": "测试职业",
                "roleType": "DAMAGE",
                "damageScore": 500,
                "isTreasureDamage": True,
                "defaultRaidParticipant": True,
                "isActive": True,
            },
            {
                "name": "工作流奶",
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
        "name": "同步新增 C",
        "profession": "测试职业",
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
assert "PLAYER_WAVE_CAPACITY_INSUFFICIENT" in {issue["code"] for issue in workflow_report["issues"]}
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
assert published_schedule["version"]["snapshot"]["schemaVersion"] == 1
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
request("/auth/logout", "POST")
print("stage 4.2 editor, publication, PNG export and sharing workflow smoke passed")
