import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

describe("SchedulePage", () => {
  it("opens the readonly wave layout from the schedule list", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/schedules") return { items: [summary], total: 1 };
      if (path === "/dungeons") return { items: [], total: 0 };
      if (path === "/schedules/schedule-1") {
        return {
          ...summary,
          note: null,
          participants: [],
          preferences: [],
          waves: [
            {
              id: "wave-1",
              waveNo: 1,
              isLocked: false,
              damageTotal: "0",
              bufferTotal: "0",
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
      }
      throw new Error(`unexpected API path: ${path}`);
    });

    render(
      <SchedulePage onError={vi.fn()} onSuccess={vi.fn()} />,
    );

    fireEvent.click(await screen.findByText("周六团"));

    expect(await screen.findByText("第 1 波")).toBeInTheDocument();
    expect(screen.getByText("红队")).toBeInTheDocument();
    expect(screen.getByText("位置 1 · 待排")).toBeInTheDocument();
  });
});
