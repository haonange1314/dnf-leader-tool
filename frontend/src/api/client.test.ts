import { afterEach, describe, expect, it, vi } from "vitest";
import { api, setScheduleEditLockToken } from "./client";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "dnf_csrf=; Max-Age=0; Path=/";
    setScheduleEditLockToken("schedule-1", null);
  });

  it("attaches the readable CSRF cookie to unsafe requests", async () => {
    document.cookie = "dnf_csrf=test-csrf-token; Path=/";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api<{ ok: boolean }>("/players", {
      method: "POST",
      body: JSON.stringify({ displayName: "测试" }),
    });

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("test-csrf-token");
    expect(init?.credentials).toBe("include");
  });

  it("does not attach a CSRF header to safe requests", async () => {
    document.cookie = "dnf_csrf=test-csrf-token; Path=/";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api<{ items: unknown[] }>("/players");

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
  });

  it("attaches the matching schedule edit lock to unsafe schedule requests", async () => {
    document.cookie = "dnf_csrf=test-csrf-token; Path=/";
    setScheduleEditLockToken("schedule-1", "edit-lock-token");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ revision: 2 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api("/schedules/schedule-1/commands", { method: "POST" });

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get("X-Edit-Lock-Token")).toBe("edit-lock-token");
  });
});
