import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("shows and prefills explicitly configured development credentials", () => {
    render(
      <LoginPage
        loading={false}
        onLogin={vi.fn().mockResolvedValue(undefined)}
        developmentCredentials={{
          username: "admin",
          password: "change-me-now",
        }}
      />,
    );

    expect(screen.getByText("本地开发账号")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByText("change-me-now")).toBeInTheDocument();
    expect(screen.getByLabelText("用户名")).toHaveValue("admin");
    expect(screen.getByLabelText("密码")).toHaveValue("change-me-now");
  });
});
