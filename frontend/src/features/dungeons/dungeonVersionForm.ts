import type {
  DungeonRoleType,
  DungeonVersion,
  DungeonVersionInput,
  FormulaDefinition,
} from "../../api/client";

export interface TeamFormValue {
  teamKey: string;
  displayName: string;
  displayColor: string;
  memberCount: number;
  strengthRank: number | null;
}

export interface CompositionFormValue {
  code: string;
  applicableTeamKeys: string[];
  damageCount: number;
  bufferCount: number;
  priority: number;
}

export interface StrengthOrderFormValue {
  metric: DungeonRoleType;
  teamKeys: string[];
}

export interface DungeonVersionFormValues {
  defaultWaveCount: number;
  minWaveCount: number;
  maxWaveCount: number | null;
  teams: TeamFormValue[];
  compositions: CompositionFormValue[];
  treasureRuleEnabled: boolean;
  treasureCount: number;
  treasureTargetTeamKey: string | null;
  treasureRequired: boolean;
  treasureCompanionOptimization: boolean;
  strengthOrders: StrengthOrderFormValue[];
  balanceMetrics: DungeonRoleType[];
  respectPlayerPreferences: boolean;
  missingSlotMode: "FILL_EARLIER_WAVES" | "SPREAD_EVENLY";
}

export const DEFAULT_FORMULA: FormulaDefinition = {
  code: "TEAM_SCORE",
  version: 2,
  damageUnit: "YI",
  damageScale: 100,
  bufferScale: 100,
  teamDamageMode: "SUM",
  twoBufferMode: "SUM",
};

export function defaultDungeonVersionForm(): DungeonVersionFormValues {
  const teamKeys = ["RED", "YELLOW", "GREEN"];
  return {
    defaultWaveCount: 12,
    minWaveCount: 1,
    maxWaveCount: 50,
    teams: [
      {
        teamKey: "RED",
        displayName: "红队",
        displayColor: "#e5484d",
        memberCount: 4,
        strengthRank: 1,
      },
      {
        teamKey: "YELLOW",
        displayName: "黄队",
        displayColor: "#f5a524",
        memberCount: 4,
        strengthRank: 2,
      },
      {
        teamKey: "GREEN",
        displayName: "绿队",
        displayColor: "#30a46c",
        memberCount: 4,
        strengthRank: 3,
      },
    ],
    compositions: [
      {
        code: "3D1B",
        applicableTeamKeys: teamKeys,
        damageCount: 3,
        bufferCount: 1,
        priority: 1,
      },
      {
        code: "2D2B",
        applicableTeamKeys: teamKeys,
        damageCount: 2,
        bufferCount: 2,
        priority: 2,
      },
    ],
    treasureRuleEnabled: true,
    treasureCount: 1,
    treasureTargetTeamKey: "RED",
    treasureRequired: true,
    treasureCompanionOptimization: true,
    strengthOrders: [
      { metric: "DAMAGE", teamKeys },
      { metric: "BUFFER", teamKeys },
    ],
    balanceMetrics: ["DAMAGE", "BUFFER"],
    respectPlayerPreferences: true,
    missingSlotMode: "FILL_EARLIER_WAVES",
  };
}

export function dungeonVersionToForm(version: DungeonVersion): DungeonVersionFormValues {
  const treasureRule = version.specialRoleRules.rules.find(
    (rule) => rule.characterFlag === "TREASURE_DAMAGE",
  );
  return {
    defaultWaveCount: version.defaultWaveCount,
    minWaveCount: version.minWaveCount,
    maxWaveCount: version.maxWaveCount,
    teams: [...version.teams]
      .sort((left, right) => left.displayOrder - right.displayOrder)
      .map((team) => ({
        teamKey: team.teamKey,
        displayName: team.displayName,
        displayColor: team.displayColor,
        memberCount: team.memberCount,
        strengthRank: team.strengthRank,
      })),
    compositions: version.compositionRules.allowed.map((rule) => ({
      code: rule.code,
      applicableTeamKeys: rule.applicableTeamKeys,
      damageCount: rule.roles.DAMAGE ?? 0,
      bufferCount: rule.roles.BUFFER ?? 0,
      priority: rule.priority,
    })),
    treasureRuleEnabled: Boolean(treasureRule),
    treasureCount: treasureRule?.countPerWave ?? 1,
    treasureTargetTeamKey: treasureRule?.targetTeamKey ?? version.teams[0]?.teamKey ?? null,
    treasureRequired: treasureRule?.requiredForCompleteWave ?? true,
    treasureCompanionOptimization: Boolean(treasureRule?.companionPolicy),
    strengthOrders: version.strengthOrderRules.orders.map((order) => ({
      metric: order.metric,
      teamKeys: [...order.teams],
    })),
    balanceMetrics: version.optimizationRules.balanceAcrossWaves,
    respectPlayerPreferences: version.optimizationRules.respectPlayerPreferences,
    missingSlotMode: version.missingSlotPolicy.mode,
  };
}

export function dungeonVersionFormToInput(
  values: DungeonVersionFormValues,
  formula: FormulaDefinition,
): DungeonVersionInput {
  const teams = values.teams.map((team, displayOrder) => ({
    ...team,
    teamKey: team.teamKey.trim().toUpperCase(),
    displayName: team.displayName.trim(),
    displayColor: team.displayColor.trim(),
    displayOrder,
    strengthRank: team.strengthRank || null,
  }));
  return {
    defaultWaveCount: values.defaultWaveCount,
    minWaveCount: values.minWaveCount,
    maxWaveCount: values.maxWaveCount || null,
    formula,
    teams,
    compositionRules: {
      schemaVersion: 1,
      allowed: values.compositions.map((rule) => ({
        code: rule.code.trim().toUpperCase(),
        applicableTeamKeys: rule.applicableTeamKeys.map((key) => key.toUpperCase()),
        roles: {
          ...(rule.damageCount > 0 ? { DAMAGE: rule.damageCount } : {}),
          ...(rule.bufferCount > 0 ? { BUFFER: rule.bufferCount } : {}),
        },
        priority: rule.priority,
      })),
    },
    specialRoleRules: {
      schemaVersion: 1,
      rules:
        values.treasureRuleEnabled && values.treasureTargetTeamKey
          ? [
              {
                code: "TREASURE_DAMAGE_CORE",
                characterFlag: "TREASURE_DAMAGE",
                countPerWave: values.treasureCount,
                targetTeamKey: values.treasureTargetTeamKey.toUpperCase(),
                requiredForCompleteWave: values.treasureRequired,
                companionPolicy: values.treasureCompanionOptimization
                  ? {
                      roleType: "DAMAGE",
                      objective: "MINIMIZE_OTHER_MEMBER_SCORE",
                    }
                  : null,
              },
            ]
          : [],
    },
    strengthOrderRules: {
      schemaVersion: 1,
      orders: values.strengthOrders.map((order) => ({
        metric: order.metric,
        teams: order.teamKeys.map((key) => key.trim().toUpperCase()),
      })),
    },
    optimizationRules: {
      schemaVersion: 1,
      balanceAcrossWaves: values.balanceMetrics,
      respectPlayerPreferences: values.respectPlayerPreferences,
    },
    missingSlotPolicy: {
      schemaVersion: 1,
      mode: values.missingSlotMode,
    },
  };
}

export function versionFormWarnings(values: DungeonVersionFormValues): string[] {
  const warnings: string[] = [];
  if (
    values.maxWaveCount !== null &&
    values.maxWaveCount < values.minWaveCount
  ) {
    warnings.push("最多波数不能小于最少波数");
  }
  if (
    values.defaultWaveCount < values.minWaveCount ||
    (values.maxWaveCount !== null &&
      values.defaultWaveCount > values.maxWaveCount)
  ) {
    warnings.push("默认波数必须位于允许范围内");
  }
  const teamKeys = values.teams.map((team) =>
    String(team?.teamKey ?? "").trim().toUpperCase(),
  );
  if (new Set(teamKeys).size !== teamKeys.length) warnings.push("队伍标识不能重复");
  const ranks = values.teams
    .map((team) => team.strengthRank)
    .filter((rank): rank is number => typeof rank === "number");
  if (new Set(ranks).size !== ranks.length) warnings.push("已填写的队伍强度排名不能重复");
  const strengthOrders = values.strengthOrders ?? [];
  const strengthMetrics = strengthOrders.map((order) => order.metric);
  if (new Set(strengthMetrics).size !== strengthMetrics.length) {
    warnings.push("同一种强度指标只能配置一条顺序规则");
  }
  for (const order of strengthOrders) {
    const orderKeys = order.teamKeys.map((key) => String(key).trim().toUpperCase());
    if (new Set(orderKeys).size !== orderKeys.length) {
      warnings.push(`${order.metric === "DAMAGE" ? "C" : "奶"}强度顺序中的队伍不能重复`);
    }
    const unknown = orderKeys.filter((key) => !teamKeys.includes(key));
    if (unknown.length) {
      warnings.push(
        `${order.metric === "DAMAGE" ? "C" : "奶"}强度顺序引用了不存在的队伍：${unknown.join("、")}`,
      );
    }
  }
  const compositionCodes = values.compositions.map((rule) =>
    String(rule?.code ?? "").trim().toUpperCase(),
  );
  if (new Set(compositionCodes).size !== compositionCodes.length) {
    warnings.push("组成规则标识不能重复");
  }
  for (const rule of values.compositions) {
    const ruleCode = String(rule?.code ?? "") || "未命名";
    const damageCount = Number(rule?.damageCount || 0);
    const bufferCount = Number(rule?.bufferCount || 0);
    if (damageCount + bufferCount <= 0) {
      warnings.push(`组成 ${ruleCode} 至少需要一名 C 或奶`);
      continue;
    }
    for (const teamKey of rule?.applicableTeamKeys ?? []) {
      const team = values.teams.find(
        (item) =>
          String(item?.teamKey ?? "").trim().toUpperCase() ===
          String(teamKey).toUpperCase(),
      );
      if (team && damageCount + bufferCount !== Number(team.memberCount || 0)) {
        warnings.push(`组成 ${ruleCode} 与 ${team.displayName}人数不一致`);
      }
    }
  }
  const coveredKeys = new Set(
    values.compositions.flatMap((rule) =>
      (rule?.applicableTeamKeys ?? []).map((key) => String(key).toUpperCase()),
    ),
  );
  const uncovered = values.teams.filter(
    (team) =>
      !coveredKeys.has(String(team?.teamKey ?? "").trim().toUpperCase()),
  );
  if (uncovered.length) {
    warnings.push(`这些队伍没有适用组成：${uncovered.map((team) => team.displayName).join("、")}`);
  }
  if (
    values.treasureRuleEnabled &&
    !teamKeys.includes(String(values.treasureTargetTeamKey ?? "").toUpperCase())
  ) {
    warnings.push("秘宝 C 目标队伍不存在");
  }
  return [...new Set(warnings)];
}
