import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
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
});
