import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Player } from "../../api/client";
import { PersonnelPage } from "./PersonnelPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  api: vi.fn(),
}));

const player: Player = {
  id: "player-1",
  displayName: "测试玩家",
  isActive: true,
  sortOrder: 0,
  characters: [
    {
      id: "character-1",
      playerId: "player-1",
      sortOrder: 0,
      profession: "剑魂",
      roleType: "DAMAGE",
      damageScore: "100.00",
      bufferScore: null,
      isTreasureDamage: false,
      isFixedLeadTeamBuffer: false,
      isGroupHunt: false,
      defaultRaidParticipant: true,
      note: null,
      isActive: true,
    },
  ],
};

describe("PersonnelPage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("shows Excel row errors directly in the import panel", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [], total: 0 };
      if (path === "/imports/characters/preview") {
        return {
          id: "batch-1",
          filename: "错误人员.xlsx",
          status: "PREVIEWED",
          total_rows: 1,
          summary: {
            create: 0,
            update: 0,
            ignore: 0,
            deactivate: 0,
            deactivate_players: 0,
            reactivate_players: 0,
            deactivation_fingerprint: 0,
            error: 1,
          },
          rows: [
            {
              row_no: 7,
              action: "ERROR",
              payload: { player_name: "测试玩家", profession: "剑魂" },
              errors: [{ code: "INVALID_ROLE", message: "类型必须为 C 或 奶" }],
              change_summary: null,
            },
          ],
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });

    const { container } = render(
      <PersonnelPage
        userRole="OWNER"
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    await screen.findByRole("heading", { name: "人员管理" });
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();
    fireEvent.change(fileInput!, {
      target: { files: [new File(["xlsx"], "错误人员.xlsx")] },
    });

    expect(await screen.findByText("类型必须为 C 或 奶")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认同步" })).toBeDisabled();
  });

  it("can permanently delete an unreferenced player from the page", async () => {
    vi.mocked(api).mockImplementation(async (path, options) => {
      if (path === "/players" && !options) return { items: [player], total: 1 };
      if (path === "/players/player-1" && options?.method === "DELETE") return undefined;
      throw new Error(`unexpected path: ${path}`);
    });

    render(
      <PersonnelPage
        userRole="OWNER"
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    await screen.findByText("测试玩家");
    expect(screen.queryByPlaceholderText("搜索玩家或职业")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "delete 删除" }));
    fireEvent.click(await screen.findByRole("button", { name: "永久删除" }));

    await waitFor(() =>
      expect(vi.mocked(api)).toHaveBeenCalledWith("/players/player-1", {
        method: "DELETE",
      }),
    );
  });

  it("shows compact character facts and keeps maintenance actions in a menu", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [player], total: 1 };
      throw new Error(`unexpected path: ${path}`);
    });

    render(
      <PersonnelPage
        userRole="OWNER"
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText("测试玩家"));

    expect(await screen.findByText("伤害")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
    expect(screen.getByText("参团")).toBeInTheDocument();
    const manageCharacter = screen.getByRole("button", { name: "管理角色 剑魂" });
    expect(manageCharacter).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "停用" })).not.toBeInTheDocument();
    fireEvent.click(manageCharacter);
    expect(await screen.findByText("修改角色")).toBeInTheDocument();
    expect(screen.queryByText("停用角色")).not.toBeInTheDocument();
  });

  it("shows inactive and non-participating character states", async () => {
    const inactivePlayer: Player = {
      ...player,
      characters: [
        {
          ...player.characters[0],
          defaultRaidParticipant: false,
          isActive: false,
        },
      ],
    };
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [inactivePlayer], total: 1 };
      throw new Error(`unexpected path: ${path}`);
    });

    render(
      <PersonnelPage
        userRole="OWNER"
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText("测试玩家"));

    const card = screen
      .getByRole("button", { name: "管理角色 剑魂" })
      .closest(".character-card");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("停用")).toBeInTheDocument();
    expect(within(card as HTMLElement).getByText("不参团")).toBeInTheDocument();
  });

  it("shows the exact successful full-sync changes before commit", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [], total: 0 };
      if (path === "/imports/characters/preview") {
        return {
          id: "batch-2",
          filename: "人员.xlsx",
          status: "PREVIEWED",
          total_rows: 1,
          created_at: "2026-09-04T00:00:00Z",
          committed_at: null,
          summary: {
            create: 1,
            update: 0,
            ignore: 0,
            deactivate: 1,
            deactivate_players: 0,
            reactivate_players: 0,
            deactivation_fingerprint: 1,
            error: 0,
          },
          change_details: [
            {
              action: "CREATE",
              player_name: "新玩家",
              profession: "剑魂",
              row_no: 2,
              fields: ["新增玩家", "新增角色"],
            },
            {
              action: "DEACTIVATE_CHARACTER",
              player_name: "旧玩家",
              profession: "奶妈",
              row_no: null,
              fields: ["停用角色"],
            },
          ],
          rows: [],
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });

    const { container } = render(
      <PersonnelPage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />,
    );
    await screen.findByRole("heading", { name: "人员管理" });
    fireEvent.change(container.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [new File(["xlsx"], "人员.xlsx")] },
    });

    expect(await screen.findByText("新玩家")).toBeInTheDocument();
    expect(screen.getByText("旧玩家")).toBeInTheDocument();
    expect(screen.getByText("新增玩家、新增角色")).toBeInTheDocument();
    expect(screen.getAllByText("停用角色").length).toBeGreaterThan(0);
  });

  it("loads import history and its persisted change details", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [], total: 0 };
      if (path === "/imports/characters/history?limit=10&offset=0") {
        return {
          items: [
            {
              id: "batch-history",
              filename: "历史人员.xlsx",
              status: "COMMITTED",
              total_rows: 1,
              summary: {
                create: 0,
                update: 1,
                ignore: 0,
                deactivate: 0,
                deactivate_players: 0,
                reactivate_players: 0,
                deactivation_fingerprint: 0,
                error: 0,
              },
              created_at: "2026-09-04T00:00:00Z",
              committed_at: "2026-09-04T00:01:00Z",
            },
          ],
          total: 1,
        };
      }
      if (path === "/imports/characters/batch-history") {
        return {
          id: "batch-history",
          filename: "历史人员.xlsx",
          status: "COMMITTED",
          total_rows: 1,
          created_at: "2026-09-04T00:00:00Z",
          committed_at: "2026-09-04T00:01:00Z",
          summary: {
            create: 0,
            update: 1,
            ignore: 0,
            deactivate: 0,
            deactivate_players: 0,
            reactivate_players: 0,
            deactivation_fingerprint: 0,
            error: 0,
          },
          change_details: [
            {
              action: "UPDATE",
              player_name: "历史玩家",
              profession: "剑魂",
              row_no: 2,
              fields: ["伤害"],
            },
          ],
          rows: [],
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });

    render(<PersonnelPage userRole="OWNER" onError={vi.fn()} onSuccess={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "history 导入记录" }));
    expect(await screen.findByText("历史人员.xlsx")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));
    expect(await screen.findByText("历史玩家")).toBeInTheDocument();
    expect(screen.getByText("伤害")).toBeInTheDocument();
  });

  it("keeps roster mutations disabled for a read-only account", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/players") return { items: [player], total: 1 };
      throw new Error(`unexpected path: ${path}`);
    });

    const view = render(
      <PersonnelPage
        userRole="VIEWER"
        permissions={["ROSTER_READ"]}
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(await view.findByRole("button", { name: /新增玩家/ })).toBeDisabled();
    expect(view.getByRole("button", { name: /上传并预览/ })).toBeDisabled();
    expect(view.getByRole("button", { name: /导入记录/ })).toBeDisabled();
  });
});
