import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the login entry when there is no session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status: 401 }),
    );
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "团长工作台" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "进入工作台" }),
    ).toBeInTheDocument();
  });

  it("allows an authenticated user to collapse and expand the sidebar", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "user-1",
          username: "admin",
          role_id: "role-1",
          role: "OWNER",
          role_name: "所有者",
          permissions: [],
          is_active: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<App />);

    const collapseButton = await screen.findByRole("button", {
      name: "收起侧边栏",
    });
    expect(collapseButton).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(collapseButton);

    const expandButton = screen.getByRole("button", { name: "展开侧边栏" });
    expect(expandButton).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector(".app-sider")).toHaveClass(
      "ant-layout-sider-collapsed",
    );

    fireEvent.click(expandButton);
    expect(
      screen.getByRole("button", { name: "收起侧边栏" }),
    ).toHaveAttribute("aria-expanded", "true");
  });
});
