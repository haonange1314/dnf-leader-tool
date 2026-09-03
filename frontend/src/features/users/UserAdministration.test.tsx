import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { AuditLogPage } from "./AuditLogPage";
import { RolePage } from "./RolePage";
import { UserPage } from "./UserPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  api: vi.fn(),
}));

describe("user administration", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("renders user management without mixing audit records", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.startsWith("/users?")) {
        return {
          items: [{
            id: "user-1", username: "admin", role_id: "role-1", role: "OWNER",
            role_name: "系统所有者", permissions: ["USER_WRITE", "ROLE_READ"],
            is_active: true, active_session_count: 1, last_login_at: null,
            created_at: "2026-09-03T00:00:00Z", updated_at: "2026-09-03T00:00:00Z",
          }],
          total: 1,
        };
      }
      if (path === "/roles?includeInactive=false") {
        return { items: [{ id: "role-1", code: "OWNER", name: "系统所有者", description: null, isSystem: true, isActive: true, permissionCodes: [], userCount: 1, createdAt: "2026-09-03T00:00:00Z", updatedAt: "2026-09-03T00:00:00Z" }], total: 1 };
      }
      throw new Error(`unexpected path: ${path}`);
    });
    render(<UserPage currentUserId="user-1" permissions={["USER_WRITE", "ROLE_READ"]} onError={vi.fn()} onSuccess={vi.fn()} />);
    expect(await screen.findByText("admin")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "用户管理" })).toBeInTheDocument();
    expect(screen.queryByText("操作日志")).not.toBeInTheDocument();
  });

  it("renders configurable roles and the permission catalog", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/roles") return { items: [{ id: "role-1", code: "OWNER", name: "系统所有者", description: null, isSystem: true, isActive: true, permissionCodes: ["ROLE_READ"], userCount: 1, createdAt: "2026-09-03T00:00:00Z", updatedAt: "2026-09-03T00:00:00Z" }], total: 1 };
      if (path === "/permissions") return { items: [{ id: "permission-1", code: "ROLE_READ", name: "查看角色权限", module: "系统管理", description: null }], total: 1 };
      throw new Error(`unexpected path: ${path}`);
    });
    render(<RolePage permissions={["ROLE_READ", "ROLE_WRITE"]} onError={vi.fn()} onSuccess={vi.fn()} />);
    expect(await screen.findByText("系统所有者")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "角色与权限" })).toBeInTheDocument();
  });

  it("renders audit logs as an independent read-only page", async () => {
    vi.mocked(api).mockResolvedValue({ items: [], total: 0 });
    render(<AuditLogPage onError={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "操作日志" })).toBeInTheDocument();
    expect(screen.getByText("独立检索登录和已认证写操作，日志只读且不可修改")).toBeInTheDocument();
  });
});
