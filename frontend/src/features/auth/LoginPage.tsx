import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, Space, Typography } from "antd";

export function LoginPage({
  loading,
  onLogin,
}: {
  loading: boolean;
  onLogin: (username: string, password: string) => Promise<void>;
}) {
  return (
    <main className="login-page">
      <Card className="login-card">
        <Space direction="vertical" size={6} className="full-width">
          <Typography.Text className="eyebrow">
            DNF RAID OPERATIONS
          </Typography.Text>
          <Typography.Title level={2}>团长工作台</Typography.Title>
          <Typography.Paragraph type="secondary">
            登录后管理副本规则与参团人员。
          </Typography.Paragraph>
        </Space>
        <Form
          layout="vertical"
          onFinish={(values) => onLogin(values.username, values.password)}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true }]}>
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
