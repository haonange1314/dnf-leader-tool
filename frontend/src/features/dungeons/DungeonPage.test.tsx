import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Dungeon } from "../../api/client";
import { DungeonPage } from "./DungeonPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  api: vi.fn(),
}));

const emptyDungeon: Dungeon = {
  id: "dungeon-empty",
  code: "RAID_EMPTY",
  name: "待配置团本",
  description: null,
  isActive: true,
  versions: [],
};

describe("DungeonPage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it(
    "lets an Owner create the first structured draft for an empty dungeon",
    async () => {
      vi.mocked(api).mockImplementation(async (path: string, options) => {
        if (path === "/dungeons" && !options) return { items: [emptyDungeon], total: 1 };
        if (path === "/dungeons/dungeon-empty/versions") return {};
        throw new Error(`unexpected API path: ${path}`);
      });

      render(
        <DungeonPage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />,
      );

      fireEvent.click(await screen.findByRole("button", { name: /创建首个草稿/ }));
      expect(
        await screen.findByText("创建 待配置团本 的首个草稿"),
      ).toBeInTheDocument();
      expect(screen.getByText("每波人数")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /保存草稿/ }));

      await waitFor(() =>
        expect(vi.mocked(api)).toHaveBeenCalledWith(
          "/dungeons/dungeon-empty/versions",
          expect.objectContaining({ method: "POST" }),
        ),
      );
      const createCall = vi
        .mocked(api)
        .mock.calls.find(([path]) => path === "/dungeons/dungeon-empty/versions");
      const payload = JSON.parse(String(createCall?.[1]?.body));
      expect(payload.teams).toHaveLength(3);
      expect(payload.compositionRules.allowed).toHaveLength(2);
      expect(payload.specialRoleRules.rules[0].targetTeamKey).toBe("RED");
    },
    20_000,
  );

  it("keeps Viewer accounts read-only", async () => {
    vi.mocked(api).mockResolvedValue({ items: [emptyDungeon], total: 1 });

    render(
      <DungeonPage userRole="VIEWER" onError={vi.fn()} onSuccess={vi.fn()} />,
    );

    expect(await screen.findByRole("button", { name: /新建副本/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /创建首个草稿/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /编辑副本/ })).toBeDisabled();
  });
});
