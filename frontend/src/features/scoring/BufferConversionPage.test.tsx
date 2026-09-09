import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type BufferConversionVersion } from "../../api/client";
import { BufferConversionPage } from "./BufferConversionPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  api: vi.fn(),
}));

const current: BufferConversionVersion = {
  id: "buffer-conversion-1",
  version: 1,
  rules: [
    { profession: "奶爸", multiplier: "0.997" },
    { profession: "奶萝", multiplier: "1.040" },
  ],
  isActive: true,
  createdBy: null,
  createdAt: "2026-09-09T00:00:00Z",
};

describe("BufferConversionPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/buffer-conversions/current") return current;
      if (path === "/buffer-conversions/versions") {
        return { items: [current], total: 1 };
      }
      throw new Error(`unexpected path: ${path}`);
    });
  });

  afterEach(() => cleanup());

  it("shows the active rules and version history", async () => {
    render(
      <BufferConversionPage
        permissions={["BUFFER_CONVERSION_READ", "BUFFER_CONVERSION_WRITE"]}
        onError={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(await screen.findByText("当前版本 v1")).toBeInTheDocument();
    expect(screen.getByText("奶爸 × 0.997")).toBeInTheDocument();
    expect(screen.getByText("奶萝 × 1.040")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存新版本" })).toBeEnabled();
  });
});
