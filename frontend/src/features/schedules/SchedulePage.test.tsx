import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { SchedulePage } from "./SchedulePage";

vi.mock("../../api/client", () => ({ api: vi.fn() }));

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

describe("SchedulePage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("opens the readonly wave layout from the schedule list", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      throw new Error(`unexpected API path: ${path}`);
    });

    render(
      <SchedulePage onError={vi.fn()} onSuccess={vi.fn()} />,
    );

    fireEvent.click(await screen.findByText("周六团"));

    expect(await screen.findByText("第 1 波")).toBeInTheDocument();
    expect(screen.getByText(/红队/)).toBeInTheDocument();
    expect(screen.getByText("位置 1 · 待排")).toBeInTheDocument();
  });

  it("marks participant selection as unsaved and blocks stale actions", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
      throw new Error(`unexpected API path: ${path}`);
    });

    render(<SchedulePage onError={vi.fn()} onSuccess={vi.fn()} />);
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

  it("previews copy configuration before creating the new schedule", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
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

    render(<SchedulePage onError={vi.fn()} onSuccess={vi.fn()} />);
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
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") return detail;
      if (path === "/schedules/schedule-1/generation-runs") return { items: [], total: 0 };
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
              strengthOrderViolationCount: 0,
            },
            diagnostics: { solverStatus: "OPTIMAL", unassigned: [], issues: [] },
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

    render(<SchedulePage onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByText("周六团"));
    fireEvent.click(await screen.findByRole("button", { name: /自动排表/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始生成" }));

    expect(await screen.findByText("最近一次自动排表")).toBeInTheDocument();
    expect(screen.getByText("已安排 1/1")).toBeInTheDocument();
    expect(screen.getByText("本波核心")).toBeInTheDocument();
  });
});
