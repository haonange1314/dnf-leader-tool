import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type GenerationRun, type ScheduleDetail } from "../../api/client";
import {
  applyOptimisticAssignment,
  buildDropOperations,
  compareGenerationRuns,
  describeIssue,
  describeRuleParseError,
  describeRuleResolutionIssue,
  SchedulePage,
} from "./SchedulePage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  api: vi.fn(),
}));

const summary = {
  id: "schedule-1",
  name: "周六团",
  dungeonVersionId: "version-1",
  waveCount: 1,
  status: "DRAFT" as const,
  revision: 1,
  validationSummary: null,
  createdAt: "2026-08-18T00:00:00Z",
  updatedAt: "2026-08-18T00:00:00Z",
};
const detail = {
  activeRuleSetId: null,
  ...summary,
  note: null,
  participants: [
    {
      id: "participant-1",
      characterId: "character-1",
      playerIdSnapshot: "player-1",
      playerNameSnapshot: "玩家一",
      characterNameSnapshot: "角色一",
      professionSnapshot: "测试职业",
      roleTypeSnapshot: "DAMAGE" as const,
      damageScoreSnapshot: "500",
      bufferScoreSnapshot: null,
      isTreasureSnapshot: true,
      isFixedLeadTeamBufferSnapshot: false,
      isGroupHuntSnapshot: false,
      isSelected: true,
      isLocked: false,
      unassignedReason: null,
    },
  ],
  preferences: [],
  waves: [
    {
      id: "wave-1",
      waveNo: 1,
      isLocked: false,
      damageTotal: "0",
      bufferTotal: "0",
      specialAssignments: [],
      teams: [
        {
          id: "team-1",
          teamKey: "RED",
          displayNameSnapshot: "红队",
          displayColorSnapshot: "#e5484d",
          displayOrderSnapshot: 0,
          memberCountSnapshot: 1,
          strengthRankSnapshot: 1,
          damageTotal: "0",
          bufferTotal: "0",
          compositionCode: "INCOMPLETE",
          slots: [
            {
              id: "slot-1",
              slotNo: 1,
              participantId: null,
              isLocked: false,
            },
          ],
        },
      ],
    },
  ],
};
const editLock = {
  scheduleId: "schedule-1",
  held: true,
  holderUserId: "user-1",
  holderUsername: "admin",
  ownedByCurrentUser: true,
  canTakeover: false,
  acquiredAt: "2026-08-18T00:00:00Z",
  heartbeatAt: "2026-08-18T00:00:00Z",
  expiresAt: "2026-08-18T00:01:30Z",
  heartbeatIntervalSeconds: 30,
  token: "edit-lock-token",
};
const parsedRuleSet = {
  id: "rule-set-1",
  scheduleId: "schedule-1",
  inputRevision: 1,
  sourceText: "玩家一尽量安排在第 1 波",
  sourceHash: "a".repeat(64),
  contextHash: "b".repeat(64),
  status: "PARSED" as const,
  modelProvider: "DEEPSEEK",
  modelName: "deepseek-v4-flash",
  providerResponseId: "response-1",
  promptVersion: "schedule-rules-v1",
  schemaVersion: 1,
  parsedRules: [
    {
      candidateId: "R1",
      type: "PLAYER_PREFER_WAVE_RANGE",
      enforcement: "SOFT" as const,
      explanation: "玩家一优先第一波",
      playerIds: ["player-1"],
      waves: [1],
    },
  ],
  resolvedReferences: {},
  issues: [],
  createdBy: "user-1",
  confirmedBy: null,
  createdAt: "2026-08-18T00:00:00Z",
  confirmedAt: null,
};

function editLockResponse(path: string) {
  const scheduleId = path.match(/^\/schedules\/([^/]+)/)?.[1] ?? "schedule-1";
  return { ...editLock, scheduleId };
}

const emptyRuleSetList = {
  items: [],
  total: 0,
  activeRuleSetId: null,
  revision: 1,
  maxSourceChars: 2000,
  parsingEnabled: true,
};

describe("SchedulePage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("explains when distinct players cannot fill a wave", () => {
    expect(
      describeIssue({
        severity: "WARNING",
        code: "DISTINCT_PLAYER_SHORTAGE",
        message_params: { required: 12, current: 11, shortage: 1 },
      }),
    ).toBe(
      "每波需要 12 个不同玩家，当前只有 11 个，还缺 1 个；同一玩家在同一波最多使用一个角色。",
    );
  });

  it("explains natural-language ambiguity and rate limits in Chinese", () => {
    expect(
      describeRuleResolutionIssue({
        code: "RULE_SET_REFERENCE_AMBIGUOUS",
        candidateId: "R1",
        field: "characterReference",
        reference: "剑魂",
        matches: ["玩家甲/剑魂", "玩家乙/剑魂"],
      }),
    ).toContain("对应多个候选：玩家甲/剑魂、玩家乙/剑魂");

    expect(
      (describeRuleParseError(
        new ApiError("限流", 429, "RULE_PARSE_RATE_LIMITED", {
          retryAfterSeconds: 17,
        }),
      ) as Error).message,
    ).toBe("规则解析请求过于频繁，请在 17 秒后重试");
  });

  it("compares alternative seeds by the established objective priority", () => {
    const objectiveSummary: NonNullable<GenerationRun["objectiveSummary"]> = {
      assignedCount: 144,
      participantCount: 160,
      completeWaveCount: 12,
      completeTeamCount: 36,
      preferredCompositionCount: 36,
      specialRuleSatisfiedCount: 12,
      damageSpread: 100,
      bufferSpread: 10,
      strengthOrderViolationCount: 1,
    };
    const previous = {
      randomSeed: 42,
      objectiveSummary,
    } as GenerationRun;
    const current = {
      randomSeed: 43,
      objectiveSummary: {
        ...objectiveSummary,
        assignedCount: 143,
        strengthOrderViolationCount: 0,
      },
    } as GenerationRun;

    expect(compareGenerationRuns(current, previous)).toMatchObject({
      improved: false,
      declined: true,
      title: "关键指标不优于种子 42",
    });
  });

  it("opens the readonly wave layout from the schedule list", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(
      <SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />,
    );

    fireEvent.click(await screen.findByText("周六团"));

    expect(await screen.findByText("第 1 波")).toBeInTheDocument();
    expect(screen.getByText(/红队/)).toBeInTheDocument();
    expect(screen.getByText("位置 1 · 待排")).toBeInTheDocument();
  });

  it("shows the bound dungeon name and exact version in list and detail views", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") {
        return {
          items: [
            {
              id: "dungeon-1",
              code: "BUILTIN_RAID_12",
              name: "12 人团本",
              description: null,
              isActive: true,
              versions: [
                {
                  id: "version-1",
                  versionNo: 3,
                  status: "PUBLISHED",
                  defaultWaveCount: 12,
                },
              ],
            },
          ],
          total: 1,
        };
      }
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);

    expect(
      await screen.findByText("12 人团本 · 副本第 3 版 · 1 波 · 修订 1"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("周六团"));
    expect(
      await screen.findByText("12 人团本 · 副本第 3 版 · 1 波 · 修订 1 · 草稿"),
    ).toBeInTheDocument();
  });

  it("keeps Viewer accounts in read-only mode", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/lock") {
        return { ...editLock, ownedByCurrentUser: false, token: null };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="VIEWER" onError={vi.fn()} onSuccess={vi.fn()} />);
    expect(await screen.findByRole("button", { name: /新建排表/ })).toBeDisabled();
    fireEvent.click(screen.getByText("周六团"));

    expect(await screen.findByText("Viewer 账号以只读方式查看排表")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /自动排表/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /保存选择/ })).toBeDisabled();
  });

  it("requires the exact schedule name before permanently deleting an unpublished draft", async () => {
    const onSuccess = vi.fn();
    let deleted = false;
    vi.mocked(api).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") {
        return { items: deleted ? [] : [summary], total: deleted ? 0 : 1 };
      }
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1" && options?.method === "DELETE") {
        deleted = true;
        return undefined;
      }
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={onSuccess} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /更多/ }));
    fireEvent.click(await screen.findByText("永久删除"));

    const confirmButton = screen.getByRole("button", { name: "确认永久删除" });
    expect(confirmButton).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("周六团"), {
      target: { value: "周六团" },
    });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith("未发布草稿已永久删除"));
    expect(screen.getByText("还没有排表")).toBeInTheDocument();
  }, 20_000);

  it("previews and confirms natural-language scheduling rules", async () => {
    let confirmed = false;
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") {
        return {
          ...detail,
          revision: confirmed ? 2 : 1,
          activeRuleSetId: confirmed ? "rule-set-1" : null,
        };
      }
      if (path === "/schedules/schedule-1/generation-runs") {
        return { items: [], total: 0 };
      }
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets/parse") return parsedRuleSet;
      if (path === "/schedules/schedule-1/rule-sets/rule-set-1/confirm") {
        confirmed = true;
        return {
          revision: 2,
          activeRuleSetId: "rule-set-1",
          ruleSet: { ...parsedRuleSet, status: "CONFIRMED" },
        };
      }
      if (path === "/schedules/schedule-1/rule-sets") {
        return {
          items: [{ ...parsedRuleSet, status: "CONFIRMED" }],
          total: 1,
          activeRuleSetId: "rule-set-1",
          revision: 2,
          maxSourceChars: 600,
          parsingEnabled: true,
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /配置/ }));
    const sourceInput = screen.getByPlaceholderText(/韩亚尽量安排/);
    expect(sourceInput).toHaveAttribute("maxlength", "600");
    fireEvent.change(sourceInput, {
      target: { value: parsedRuleSet.sourceText },
    });
    const parseButton = screen.getByRole("button", { name: "解析要求" });
    await waitFor(() => expect(parseButton).toBeEnabled());
    fireEvent.click(parseButton);

    expect(await screen.findByText(/玩家一优先第一波/)).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", { name: "确认并用于自动排表" });
    await waitFor(() => expect(confirmButton).toBeEnabled());
    fireEvent.click(confirmButton);

    expect(await screen.findByText("已确认 1 条")).toBeInTheDocument();
    const confirmCall = vi
      .mocked(api)
      .mock.calls.find(([path]) => path.endsWith("/rule-set-1/confirm"));
    expect(JSON.parse(String(confirmCall?.[1]?.body))).toMatchObject({
      baseRevision: 1,
      sourceHash: "a".repeat(64),
      contextHash: "b".repeat(64),
    });
  }, 15_000);

  it("marks participant selection as unsaved and blocks stale actions", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("checkbox"));

    expect(screen.getByText("当前有尚未保存的排表设置")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    expect((await screen.findByText("复制排表")).closest("li")).toHaveClass(
      "ant-dropdown-menu-item-disabled",
    );
    expect(screen.getByRole("button", { name: /运行预检查/ })).toBeDisabled();
    const participantTitle = screen
      .getAllByText("参团角色")
      .find((element) => element.classList.contains("ant-statistic-title"));
    const participantStatistic = participantTitle?.closest(".ant-statistic");
    expect(participantStatistic).not.toBeNull();
    expect(within(participantStatistic as HTMLElement).getByText("0")).toBeInTheDocument();
  });

  it("keeps a large participant list collapsed until requested", async () => {
    const participants = Array.from({ length: 25 }, (_, index) => ({
      ...detail.participants[0],
      id: `participant-${index + 1}`,
      characterId: `character-${index + 1}`,
      characterNameSnapshot: `角色${index + 1}`,
    }));
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return { ...detail, participants };
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));

    expect(await screen.findByText("候选角色已收起，需要调整参团名单时再展开。")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /展开角色选择/ }));
    expect(await screen.findAllByRole("checkbox")).toHaveLength(25);
  });

  it("applies an editor lock command and exposes undo", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/commands") {
        return {
          operationId: "operation-1",
          revision: 2,
          schedule: {
            ...detail,
            revision: 2,
            waves: detail.waves.map((wave) => ({ ...wave, isLocked: true })),
          },
          inverseOperations: [{ type: "LOCK_WAVE", waveId: "wave-1", locked: false }],
        };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /锁定波次/ }));

    expect(await screen.findByRole("button", { name: /解锁波次/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /撤销/ })).toBeEnabled();
  }, 15_000);

  it("keeps the confirmed scheduling rule visible after a manual edit", async () => {
    const confirmedRuleSet = {
      ...parsedRuleSet,
      status: "CONFIRMED" as const,
      confirmedBy: "user-1",
      confirmedAt: "2026-08-18T00:00:01Z",
    };
    const detailWithRule = { ...detail, activeRuleSetId: confirmedRuleSet.id };
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detailWithRule;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/rule-sets") {
        return { ...emptyRuleSetList, items: [confirmedRuleSet], activeRuleSetId: confirmedRuleSet.id };
      }
      if (path === "/schedules/schedule-1/commands") {
        return {
          operationId: "operation-1",
          revision: 2,
          schedule: {
            ...detailWithRule,
            revision: 2,
            waves: detailWithRule.waves.map((wave) => ({ ...wave, isLocked: true })),
          },
          inverseOperations: [{ type: "LOCK_WAVE", waveId: "wave-1", locked: false }],
        };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    expect(await screen.findByText(parsedRuleSet.sourceText)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /锁定波次/ }));

    expect(await screen.findByRole("button", { name: /解锁波次/ })).toBeInTheDocument();
    expect(screen.getByText(parsedRuleSet.sourceText)).toBeInTheDocument();
  }, 15_000);

  it("previews copy configuration before creating the new schedule", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") {
        return {
          items: [
            {
              id: "dungeon-1",
              name: "测试团本",
              isActive: true,
              versions: [
                {
                  id: "version-1",
                  versionNo: 1,
                  status: "PUBLISHED",
                },
              ],
            },
          ],
          total: 1,
        };
      }
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/copy/preview") {
        return {
          revision: 1,
          sourceDungeonVersionId: "version-1",
          targetDungeonVersionId: "version-1",
          waveCount: 1,
          migrationRequired: false,
          migrationFingerprint: "a".repeat(64),
          changes: [],
        };
      }
      if (path === "/schedules/schedule-1/copy") {
        return { ...detail, id: "schedule-2", name: "周六团 - 副本" };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    await screen.findByText("第 1 波");
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    fireEvent.click(await screen.findByText("复制排表"));
    fireEvent.click(screen.getByRole("button", { name: "预览迁移" }));

    expect(await screen.findByText("副本结构与当前排表一致")).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", { name: /确认创建/ });
    await waitFor(() => expect(confirmButton).not.toHaveClass("ant-btn-loading"));
    fireEvent.click(confirmButton);
    expect(await screen.findByText("周六团 - 副本")).toBeInTheDocument();

    const copyCall = vi.mocked(api).mock.calls.find(([path]) => path.endsWith("/copy"));
    expect(copyCall).toBeDefined();
    expect(JSON.parse(String(copyCall?.[1]?.body))).toMatchObject({
      migrationFingerprint: "a".repeat(64),
      targetDungeonVersionId: "version-1",
      waveCount: 1,
    });
  }, 15_000);

  it("generates a schedule and displays the persisted solver summary", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/validate") {
        return { revision: 1, issues: [], summary: { error: 0, warning: 0, info: 0 } };
      }
      if (path === "/schedules/schedule-1/generate") {
        return {
          run: {
            id: "run-1",
            scheduleId: "schedule-1",
            inputRevision: 1,
            resultRevision: 2,
            status: "SUCCEEDED",
            inputHash: "a".repeat(64),
            solverVersion: "cp-sat-v1",
            formulaVersionId: "formula-1",
            randomSeed: 42,
            timeLimitSeconds: 10,
            durationMs: 25,
            objectiveSummary: {
              assignedCount: 1,
              participantCount: 1,
              completeWaveCount: 1,
              completeTeamCount: 1,
              preferredCompositionCount: 1,
              specialRuleSatisfiedCount: 1,
              damageSpread: 0,
              bufferSpread: 0,
              damageSpreadDisplay: "0.00",
              bufferSpreadDisplay: "0.0",
              strengthOrderViolationCount: 0,
            },
            diagnostics: {
              solverStatus: "OPTIMAL",
              objectiveStages: [
                {
                  code: "ASSIGNED_COUNT",
                  value: 1,
                  outcome: "TARGET_REACHED",
                  durationMs: 8,
                },
                {
                  code: "BALANCE_DAMAGE",
                  value: 0,
                  outcome: "OPTIMAL",
                  durationMs: 4,
                },
              ],
              unassigned: [],
              issues: [],
            },
            createdAt: "2026-08-18T00:00:00Z",
            finishedAt: "2026-08-18T00:00:01Z",
          },
          schedule: {
            ...detail,
            revision: 2,
            waves: detail.waves.map((wave) => ({
              ...wave,
              specialAssignments: [
                {
                  id: "special-1",
                  ruleCode: "TREASURE_DAMAGE_CORE",
                  participantId: "participant-1",
                  targetTeamKeySnapshot: "RED",
                },
              ],
              teams: wave.teams.map((team) => ({
                ...team,
                compositionCode: "3D1B",
                slots: team.slots.map((slot, index) => ({
                  ...slot,
                  participantId: index === 0 ? "participant-1" : null,
                })),
              })),
            })),
          },
        };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /自动排表/ }));
    fireEvent.click(await screen.findByText("高级设置"));
    expect(screen.getByText(/相同数据、规则、锁定和种子可复现/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更换方案种子" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));

    expect(await screen.findByText("最近一次自动排表")).toBeInTheDocument();
    expect(screen.getByText("已安排 1/1")).toBeInTheDocument();
    expect(screen.getByText("优先组成 1")).toBeInTheDocument();
    expect(screen.getByText("C 跨波差 0.00 亿")).toBeInTheDocument();
    expect(screen.getByText("奶跨波差 0.0")).toBeInTheDocument();
    expect(screen.getByText("安排人数 · 达到理论界")).toBeInTheDocument();
    expect(screen.getByText("C 跨波平衡 · 已证明最优")).toBeInTheDocument();
    expect(screen.getByText("本波核心")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /换一个方案/ })).toBeEnabled();
  }, 20_000);

  it("keeps the generation dialog open and applies retry suggestions after timeout", async () => {
    const onError = vi.fn();
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/validate") {
        return { revision: 1, issues: [], summary: { error: 0, warning: 0, info: 0 } };
      }
      if (path === "/schedules/schedule-1/generate") {
        throw new ApiError(
          "求解器在 10 秒时限内未找到可行排表，请增加求解时限或更换方案种子后重试",
          422,
          "SCHEDULE_GENERATION_TIMEOUT",
          { suggestedTimeLimitSeconds: 20, suggestedRandomSeed: 43 },
        );
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={onError} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /自动排表/ }));
    fireEvent.click(await screen.findByRole("button", { name: "开始生成" }));

    expect(await screen.findByText("本次求解达到时限")).toBeInTheDocument();
    expect(screen.getByText(/高级参数已更新为建议值/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("20")).toBeInTheDocument();
    expect(screen.getByDisplayValue("43")).toBeInTheDocument();
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      code: "SCHEDULE_GENERATION_TIMEOUT",
    }));
  });

  it("shows server publication issues before enabling publish", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/publication-check") {
        return {
          revision: 1,
          publishable: false,
          summary: { error: 1, warning: 0, info: 0 },
          issues: [
            {
              severity: "ERROR",
              code: "TEAM_INCOMPLETE",
              message_params: { waveNo: 1, teamKey: "RED" },
            },
          ],
        };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /发布排表/ }));

    expect(await screen.findByText("队伍存在待补位置")).toBeInTheDocument();
    expect(screen.getByText("错误 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认发布" })).toBeDisabled();
  });

  it("lists managed share links for a published version", async () => {
    const version = {
      id: "published-version-1",
      scheduleId: "schedule-1",
      versionNo: 1,
      sourceRevision: 1,
      snapshotSchemaVersion: 1,
      snapshotHash: "a".repeat(64),
      formulaVersionId: "formula-1",
      publishedAt: "2026-08-18T00:00:00Z",
    };
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules?includeArchived=false") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [version], total: 1 };
      if (path === "/schedule-versions/published-version-1/share-links") {
        return {
          items: [
            {
              id: "share-1",
              scheduleVersionId: "published-version-1",
              expiresAt: "2026-09-18T00:00:00Z",
              revokedAt: null,
              createdAt: "2026-08-18T00:00:00Z",
              status: "ACTIVE",
            },
          ],
          total: 1,
        };
      }
      if (path === "/schedules/schedule-1/rule-sets") return emptyRuleSetList;
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /发布历史/ }));
    fireEvent.click(await screen.findByRole("button", { name: /管理分享链接/ }));

    expect(await screen.findByText("有效")).toBeInTheDocument();
    expect(screen.getByText(/有效期至/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤 销" })).toBeEnabled();
  }, 15_000);
});

describe("schedule drag operations", () => {
  const occupiedDetail: ScheduleDetail = {
    ...detail,
    participants: [
      ...detail.participants,
      {
        ...detail.participants[0],
        id: "participant-2",
        characterId: "character-2",
        playerIdSnapshot: "player-2",
        playerNameSnapshot: "玩家二",
        characterNameSnapshot: "角色二",
        damageScoreSnapshot: "300",
      },
    ],
    waves: [
      {
        ...detail.waves[0],
        teams: [
          {
            ...detail.waves[0].teams[0],
            slots: [{ ...detail.waves[0].teams[0].slots[0], participantId: "participant-1" }],
          },
        ],
      },
    ],
  };

  it("replaces an occupied slot atomically when the dragged participant is unassigned", () => {
    const operations = buildDropOperations(occupiedDetail, "participant-2", "slot-1");

    expect(operations).toEqual([
      { type: "UNASSIGN_PARTICIPANT", participantId: "participant-1" },
      { type: "MOVE_PARTICIPANT", participantId: "participant-2", toSlotId: "slot-1" },
    ]);

    const optimistic = applyOptimisticAssignment(occupiedDetail, operations);
    expect(optimistic.waves[0].teams[0].slots[0].participantId).toBe("participant-2");
    expect(optimistic.waves[0].damageTotal).toBe("300");
    expect(optimistic.participants[0].unassignedReason).toEqual({
      code: "MANUALLY_UNASSIGNED",
    });
  });

  it("moves an assigned participant back to the unassigned pool optimistically", () => {
    const optimistic = applyOptimisticAssignment(occupiedDetail, [
      { type: "UNASSIGN_PARTICIPANT", participantId: "participant-1" },
    ]);

    expect(optimistic.waves[0].teams[0].slots[0].participantId).toBeNull();
    expect(optimistic.participants[0].unassignedReason).toEqual({
      code: "MANUALLY_UNASSIGNED",
    });
  });
});
