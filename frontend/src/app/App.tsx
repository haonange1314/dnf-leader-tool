import {
  DatabaseOutlined,
  LogoutOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  Button,
  ConfigProvider,
  Layout,
  Menu,
  Skeleton,
  Typography,
  message,
} from "antd";
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

const { Content, Header, Sider } = Layout;

export function App() {
  const shareToken = window.location.pathname.match(/^\/share\/([^/]+)$/)?.[1] ?? null;
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [section, setSection] = useState("dungeons");
  const [messageApi, contextHolder] = message.useMessage();
  useEffect(() => {
    if (shareToken) {
      setChecking(false);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, [shareToken]);
  const onError = (error: unknown) =>
    messageApi.error(error instanceof Error ? error.message : "操作失败");
  const login = async (username: string, password: string) => {
    setLoginLoading(true);
    try {
      setUser(
        await api<User>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ username, password }),
        }),
      );
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
      theme={{
        token: {
          colorPrimary: "#d44a3a",
          borderRadius: 12,
          colorBgLayout: "#f2f0eb",
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
              <span className="brand-mark">
                <TeamOutlined />
              </span>
              <div>
                <Typography.Text className="app-title">
                  DNF 团长排表工具
                </Typography.Text>
                <Typography.Text className="app-subtitle">
                  阶段 4 · 完整编辑与发布
                </Typography.Text>
              </div>
            </div>
            <div className="user-actions">
              <Typography.Text className="user-name">
                {user.username} · {user.role}
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
              width={220}
              className="app-sider"
            >
              <Menu
                mode="inline"
                selectedKeys={[section]}
                onSelect={({ key }) => setSection(key)}
                items={[
                  {
                    key: "dungeons",
                    icon: <DatabaseOutlined />,
                    label: "副本管理",
                  },
                  {
                    key: "personnel",
                    icon: <TeamOutlined />,
                    label: "人员管理",
                  },
                  {
                    key: "schedules",
                    icon: <TeamOutlined />,
                    label: "排表管理",
                  },
                ]}
              />
            </Sider>
            <Content className="app-content">
              <Suspense fallback={<Skeleton active />}>
                {section === "dungeons" ? (
                  <DungeonPage
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : section === "personnel" ? (
                  <PersonnelPage
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                ) : (
                  <SchedulePage
                    onError={onError}
                    onSuccess={messageApi.success}
                  />
                )}
              </Suspense>
            </Content>
          </Layout>
        </Layout>
      )}
    </ConfigProvider>
  );
}
