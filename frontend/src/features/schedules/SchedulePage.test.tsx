import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ScheduleDetail } from "../../api/client";
import { applyOptimisticAssignment, buildDropOperations, SchedulePage } from "./SchedulePage";

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

function editLockResponse(path: string) {
  const scheduleId = path.match(/^\/schedules\/([^/]+)/)?.[1] ?? "schedule-1";
  return { ...editLock, scheduleId };
}

describe("SchedulePage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("opens the readonly wave layout from the schedule list", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
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
      if (path === "/schedules") return { items: [summary], total: 1 };
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
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/lock") {
        return { ...editLock, ownedByCurrentUser: false, token: null };
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="VIEWER" onError={vi.fn()} onSuccess={vi.fn()} />);
    expect(await screen.findByRole("button", { name: /新建排表/ })).toBeDisabled();
    fireEvent.click(screen.getByText("周六团"));

    expect(await screen.findByText("Viewer 账号以只读方式查看排表")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /自动排表/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /保存选择/ })).toBeDisabled();
  });

  it("marks participant selection as unsaved and blocks stale actions", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("checkbox"));

    expect(screen.getByText("当前有尚未保存的排表设置")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /复制排表/ })).toBeDisabled();
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
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return { ...detail, participants };
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
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
      if (path === "/schedules") return { items: [summary], total: 1 };
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
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /锁定波次/ }));

    expect(await screen.findByRole("button", { name: /解锁波次/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /撤销/ })).toBeEnabled();
  });

  it("previews copy configuration before creating the new schedule", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules") return { items: [summary], total: 1 };
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
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    await screen.findByText("第 1 波");
    fireEvent.click(screen.getByRole("button", { name: /复制排表/ }));
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
  });

  it("generates a schedule and displays the persisted solver summary", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1/versions") return { items: [], total: 0 };
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
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /自动排表/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));

    expect(await screen.findByText("最近一次自动排表")).toBeInTheDocument();
    expect(screen.getByText("已安排 1/1")).toBeInTheDocument();
    expect(screen.getByText("优先组成 1")).toBeInTheDocument();
    expect(screen.getByText("C 跨波差 0.00 亿")).toBeInTheDocument();
    expect(screen.getByText("奶跨波差 0.0")).toBeInTheDocument();
    expect(screen.getByText("安排人数 · 达到理论界")).toBeInTheDocument();
    expect(screen.getByText("C 跨波平衡 · 已证明最优")).toBeInTheDocument();
    expect(screen.getByText("本波核心")).toBeInTheDocument();
  });

  it("shows server publication issues before enabling publish", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.endsWith("/lock")) return editLockResponse(path);
      if (path === "/schedules") return { items: [summary], total: 1 };
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
      if (path === "/schedules") return { items: [summary], total: 1 };
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
});
