import {
  CalendarOutlined,
  CrownOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Button,
  ConfigProvider,
  Empty,
  Layout,
  Menu,
  Skeleton,
  Typography,
  message,
  theme as antdTheme,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import { lazy, Suspense, useEffect, useState } from "react";
import { api, type User } from "../api/client";
import { LoginPage } from "../features/auth/LoginPage";
import { PublicSchedulePage } from "../features/schedules/PublicSchedulePage";

const DungeonPage = lazy(() =>
  import("../features/dungeons/DungeonPage").then((module) => ({
    default: module.DungeonPage,
  })),
);
const PersonnelPage = lazy(() =>
  import("../features/personnel/PersonnelPage").then((module) => ({
    default: module.PersonnelPage,
  })),
);
const SchedulePage = lazy(() =>
  import("../features/schedules/SchedulePage").then((module) => ({
    default: module.SchedulePage,
  })),
);
const UserPage = lazy(() =>
  import("../features/users/UserPage").then((module) => ({
    default: module.UserPage,
  })),
);
const RolePage = lazy(() =>
  import("../features/users/RolePage").then((module) => ({ default: module.RolePage })),
);
const AuditLogPage = lazy(() =>
  import("../features/users/AuditLogPage").then((module) => ({ default: module.AuditLogPage })),
);

const { Content, Header, Sider } = Layout;

function firstAllowedSection(user: User): string {
  const entries = [
    ["DUNGEON_READ", "dungeons"],
    ["ROSTER_READ", "personnel"],
    ["SCHEDULE_READ", "schedules"],
    ["USER_READ", "users"],
    ["ROLE_READ", "roles"],
    ["AUDIT_READ", "audit"],
  ];
  return entries.find(([permission]) => user.permissions.includes(permission))?.[1] ?? "none";
}

export function App() {
  const shareToken = window.location.pathname.match(/^\/share\/([^/]+)$/)?.[1] ?? null;
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [section, setSection] = useState("dungeons");
  const [siderCollapsed, setSiderCollapsed] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();
  useEffect(() => {
    if (shareToken) {
      setChecking(false);
      return;
    }
    api<User>("/auth/me")
      .then((currentUser) => {
        setUser(currentUser);
        setSection(firstAllowedSection(currentUser));
      })
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, [shareToken]);
  const onError = (error: unknown) =>
    messageApi.error(error instanceof Error ? error.message : "操作失败");
  const login = async (username: string, password: string) => {
    setLoginLoading(true);
    try {
      const currentUser = await api<User>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ username, password }),
        });
      setUser(currentUser);
      setSection(firstAllowedSection(currentUser));
    } catch (error) {
      onError(error);
    } finally {
      setLoginLoading(false);
    }
  };
  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
  };
  return (
    <ConfigProvider
      componentSize="small"
      locale={zhCN}
      theme={{
        algorithm: antdTheme.compactAlgorithm,
        token: {
          colorPrimary: "#0071e3",
          colorInfo: "#0071e3",
          colorText: "#1d1d1f",
          colorTextSecondary: "#6e6e73",
          colorBorder: "#d2d2d7",
          colorBorderSecondary: "#e5e5ea",
          colorBgLayout: "#f5f5f7",
          colorBgContainer: "rgba(255, 255, 255, 0.92)",
          borderRadius: 10,
          borderRadiusLG: 14,
          controlHeight: 32,
          controlHeightSM: 28,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", Arial, sans-serif',
          boxShadowTertiary: "0 8px 28px rgb(0 0 0 / 5%)",
        },
        components: {
          Button: {
            borderRadius: 9,
            defaultShadow: "none",
            primaryShadow: "none",
          },
          Card: {
            bodyPadding: 14,
            bodyPaddingSM: 10,
            headerHeight: 40,
            headerFontSize: 14,
          },
          Layout: {
            bodyBg: "#f5f5f7",
            headerBg: "rgba(250, 250, 252, 0.86)",
            siderBg: "rgba(250, 250, 252, 0.88)",
          },
          Menu: {
            itemHeight: 34,
            itemBorderRadius: 9,
            itemSelectedBg: "#e8f2ff",
            itemSelectedColor: "#0066cc",
          },
          Table: {
            cellPaddingBlock: 8,
            cellPaddingBlockSM: 6,
            cellPaddingInline: 10,
            cellPaddingInlineSM: 8,
            headerBg: "#f5f5f7",
          },
          Segmented: {
            itemSelectedBg: "#ffffff",
          },
        },
      }}
    >
      {contextHolder}
      {shareToken ? (
        <PublicSchedulePage token={shareToken} />
      ) : checking ? (
        <main className="loading-page">
          <Skeleton active />
        </main>
      ) : !user ? (
        <LoginPage loading={loginLoading} onLogin={login} />
      ) : (
        <Layout className="app-shell">
          <Header className="app-header">
            <div className="brand">
              <Button
                type="text"
                className="sider-toggle-button"
                icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                aria-label={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
                aria-controls="primary-navigation"
                aria-expanded={!siderCollapsed}
                title={siderCollapsed ? "展开侧边栏" : "收起侧边栏"}
                onClick={() => setSiderCollapsed((collapsed) => !collapsed)}
              />
              <span className="brand-mark">
                <CrownOutlined />
              </span>
              <div>
                <Typography.Text className="app-title">
                  DNF 团长排表工具
                </Typography.Text>
                <Typography.Text className="app-subtitle">
                  12 人团本 · 智能排表工作台
                </Typography.Text>
              </div>
            </div>
            <div className="user-actions">
              <Typography.Text className="user-name">
                {user.username} · {user.role_name}
              </Typography.Text>
              <Button type="text" icon={<LogoutOutlined />} onClick={logout}>
                退出
              </Button>
            </div>
          </Header>
          <Layout>
            <Sider
              breakpoint="lg"
              collapsedWidth="0"
              collapsed={siderCollapsed}
              onCollapse={setSiderCollapsed}
              trigger={null}
              width={188}
              className="app-sider"
            >
              <Menu
                id="primary-navigation"
                mode="inline"
                selectedKeys={[section]}
                onSelect={({ key }) => setSection(key)}
                items={[
                  ...(user.permissions.includes("DUNGEON_READ") ? [{
                    key: "dungeons",
                    icon: <DatabaseOutlined />,
                    label: "副本管理",
                  }] : []),
                  ...(user.permissions.includes("ROSTER_READ") ? [{
                    key: "personnel",
                    icon: <TeamOutlined />,
                    label: "人员管理",
                  }] : []),
                  ...(user.permissions.includes("SCHEDULE_READ") ? [{
                    key: "schedules",
                    icon: <CalendarOutlined />,
                    label: "排表管理",
                  }] : []),
                  ...(user.permissions.includes("USER_READ") ? [{ key: "users", icon: <UserOutlined />, label: "用户管理" }] : []),
                  ...(user.permissions.includes("ROLE_READ") ? [{ key: "roles", icon: <SafetyCertificateOutlined />, label: "角色与权限" }] : []),
                  ...(user.permissions.includes("AUDIT_READ") ? [{ key: "audit", icon: <FileSearchOutlined />, label: "操作日志" }] : []),
                ]}
              />
            </Sider>
            <Content className="app-content">
              <Suspense fallback={<Skeleton active />}>
                {section === "dungeons" ? (
                  <DungeonPage
                    userRole={user.role}
                    permissions={user.permissions}
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : section === "personnel" ? (
                  <PersonnelPage
                    userRole={user.role}
                    permissions={user.permissions}
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : section === "schedules" ? (
                  <SchedulePage
                    userRole={user.role}
                    permissions={user.permissions}
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : section === "users" ? (
                  <UserPage
                    currentUserId={user.id}
                    permissions={user.permissions}
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : section === "roles" ? (
                  <RolePage permissions={user.permissions} onError={onError} onSuccess={messageApi.success} />
                ) : section === "audit" ? (
                  <AuditLogPage onError={onError} />
                ) : (
                  <Empty description="当前角色没有可访问的功能，请联系管理员分配权限" />
                )}
              </Suspense>
            </Content>
          </Layout>
        </Layout>
      )}
    </ConfigProvider>
  );
}
