import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";

export type DevelopmentCredentials = {
  username: string;
  password: string;
};

const configuredDevelopmentCredentials: DevelopmentCredentials | null =
  import.meta.env.VITE_SHOW_DEV_LOGIN === "true" &&
  import.meta.env.VITE_DEV_LOGIN_ACCOUNT &&
  import.meta.env.VITE_DEV_LOGIN_CODE
    ? {
        username: import.meta.env.VITE_DEV_LOGIN_ACCOUNT,
        password: import.meta.env.VITE_DEV_LOGIN_CODE,
      }
    : null;

export function LoginPage({
  loading,
  onLogin,
  developmentCredentials = configuredDevelopmentCredentials,
}: {
  loading: boolean;
  onLogin: (username: string, password: string) => Promise<void>;
  developmentCredentials?: DevelopmentCredentials | null;
}) {
  return (
    <main className="login-page">
      <Card className="login-card">
        <Space orientation="vertical" size={6} className="full-width">
          <Typography.Text className="eyebrow">
            DNF RAID OPERATIONS
          </Typography.Text>
          <Typography.Title level={2}>团长工作台</Typography.Title>
          <Typography.Paragraph type="secondary">
            登录后管理副本规则与参团人员。
          </Typography.Paragraph>
        </Space>
        {developmentCredentials ? (
          <Alert
            className="dev-login-hint"
            type="info"
            showIcon
            title="本地开发账号"
            description={
              <Space orientation="vertical" size={2}>
                <span>
                  账号：
                  <Typography.Text code>
                    {developmentCredentials.username}
                  </Typography.Text>
                </span>
                <span>
                  密码：
                  <Typography.Text code>
                    {developmentCredentials.password}
                  </Typography.Text>
                </span>
              </Space>
            }
          />
        ) : null}
        <Form
          layout="vertical"
          onFinish={(values) => onLogin(values.username, values.password)}
        >
          <Form.Item
            label="用户名"
            name="username"
            initialValue={developmentCredentials?.username}
            rules={[{ required: true }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            initialValue={developmentCredentials?.password}
            rules={[{ required: true }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              autoComplete="current-password"
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            block
            size="large"
          >
            进入工作台
          </Button>
        </Form>
      </Card>
    </main>
  );
}
