import { describe, expect, it } from "vitest";
import type { DungeonVersion } from "../../api/client";
import {
  DEFAULT_FORMULA,
  defaultDungeonVersionForm,
  dungeonVersionFormToInput,
  dungeonVersionToForm,
  versionFormWarnings,
} from "./dungeonVersionForm";

describe("dungeon version form mapping", () => {
  it("builds the default 12-person raid through the generic version contract", () => {
    const values = defaultDungeonVersionForm();
    const payload = dungeonVersionFormToInput(values, DEFAULT_FORMULA);

    expect(payload.defaultWaveCount).toBe(12);
    expect(payload.teams.map((team) => team.teamKey)).toEqual([
      "RED",
      "YELLOW",
      "GREEN",
    ]);
    expect(payload.teams.reduce((sum, team) => sum + team.memberCount, 0)).toBe(12);
    expect(payload.compositionRules.allowed.map((rule) => rule.roles)).toEqual([
      { DAMAGE: 3, BUFFER: 1 },
      { DAMAGE: 2, BUFFER: 2 },
    ]);
    expect(payload.strengthOrderRules.orders).toEqual([
      { metric: "DAMAGE", teams: ["RED", "YELLOW", "GREEN"] },
      { metric: "BUFFER", teams: ["RED", "YELLOW", "GREEN"] },
    ]);
    expect(payload.specialRoleRules.rules[0]).toMatchObject({
      characterFlag: "TREASURE_DAMAGE",
      targetTeamKey: "RED",
    });
    expect(versionFormWarnings(values)).toEqual([]);
  });

  it("round-trips a custom single-team four-person dungeon", () => {
    const version: DungeonVersion = {
      id: "version-1",
      dungeonId: "dungeon-1",
      versionNo: 1,
      status: "PUBLISHED",
      defaultWaveCount: 1,
      minWaveCount: 1,
      maxWaveCount: 12,
      formula: { ...DEFAULT_FORMULA, version: 1, bufferScale: 10 },
      teams: [
        {
          id: "team-1",
          teamKey: "PARTY",
          displayName: "队伍",
          displayColor: "#3e63dd",
          displayOrder: 0,
          memberCount: 4,
          strengthRank: null,
        },
      ],
      compositionRules: {
        schemaVersion: 1,
        allowed: [
          {
            code: "3D1B",
            applicableTeamKeys: ["PARTY"],
            roles: { DAMAGE: 3, BUFFER: 1 },
            priority: 1,
          },
        ],
      },
      specialRoleRules: { schemaVersion: 1, rules: [] },
      strengthOrderRules: { schemaVersion: 1, orders: [] },
      optimizationRules: {
        schemaVersion: 1,
        balanceAcrossWaves: [],
        respectPlayerPreferences: true,
      },
      missingSlotPolicy: { schemaVersion: 1, mode: "FILL_EARLIER_WAVES" },
      createdAt: "2026-09-01T00:00:00Z",
      publishedAt: "2026-09-01T00:00:00Z",
    };

    const payload = dungeonVersionFormToInput(
      dungeonVersionToForm(version),
      version.formula,
    );

    expect(payload.teams).toHaveLength(1);
    expect(payload.teams[0]).toMatchObject({ teamKey: "PARTY", memberCount: 4 });
    expect(payload.specialRoleRules.rules).toEqual([]);
    expect(payload.strengthOrderRules.orders).toEqual([]);
  });

  it("reports uncovered teams and composition capacity mismatches before saving", () => {
    const values = defaultDungeonVersionForm();
    values.compositions = [
      {
        code: "INVALID",
        applicableTeamKeys: ["RED"],
        damageCount: 4,
        bufferCount: 1,
        priority: 1,
      },
    ];

    expect(versionFormWarnings(values)).toEqual(
      expect.arrayContaining([
        "组成 INVALID 与 红队人数不一致",
        "这些队伍没有适用组成：黄队、绿队",
      ]),
    );
  });

  it("reports invalid wave ranges and stale treasure targets", () => {
    const values = defaultDungeonVersionForm();
    values.minWaveCount = 8;
    values.maxWaveCount = 6;
    values.defaultWaveCount = 7;
    values.treasureTargetTeamKey = "REMOVED_TEAM";

    expect(versionFormWarnings(values)).toEqual(
      expect.arrayContaining([
        "最多波数不能小于最少波数",
        "默认波数必须位于允许范围内",
        "秘宝 C 目标队伍不存在",
      ]),
    );
  });

  it("preserves independent strength orders for each metric", () => {
    const values = defaultDungeonVersionForm();
    values.strengthOrders = [
      { metric: "DAMAGE", teamKeys: ["RED", "YELLOW", "GREEN"] },
      { metric: "BUFFER", teamKeys: ["YELLOW", "RED"] },
    ];

    const payload = dungeonVersionFormToInput(values, DEFAULT_FORMULA);

    expect(payload.strengthOrderRules.orders).toEqual([
      { metric: "DAMAGE", teams: ["RED", "YELLOW", "GREEN"] },
      { metric: "BUFFER", teams: ["YELLOW", "RED"] },
    ]);
  });
});
