import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { api, type AuditLog, type User } from "../../api/client";

interface Props {
  currentUserId: string;
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

interface UserFormValues {
  username: string;
  password?: string;
  role: User["role"];
  isActive: boolean;
}

const ROLE_LABELS: Record<User["role"], string> = {
  OWNER: "Owner",
  EDITOR: "编辑者",
  VIEWER: "查看者",
};

export function UserPage({ currentUserId, onError, onSuccess }: Props) {
  const [users, setUsers] = useState<User[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [editing, setEditing] = useState<User | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [form] = Form.useForm<UserFormValues>();
  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);

  const load = async () => {
    try {
      const [userResult, auditResult] = await Promise.all([
        api<{ items: User[]; total: number }>("/users"),
        api<{ items: AuditLog[]; total: number }>("/audit-logs?limit=100"),
      ]);
      setUsers(userResult.items);
      setAuditLogs(auditResult.items);
      setAuditTotal(auditResult.total);
    } catch (error) {
      onError(error);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({ username: "", password: "", role: "EDITOR", isActive: true });
    setModalOpen(true);
  };

  const openEdit = (user: User) => {
    setEditing(user);
    form.setFieldsValue({
      username: user.username,
      password: "",
      role: user.role,
      isActive: user.is_active,
    });
    setModalOpen(true);
  };

  const save = async (values: UserFormValues) => {
    setPending(true);
    try {
      if (editing) {
        await api<User>(`/users/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            role: values.role,
            isActive: values.isActive,
            ...(values.password ? { password: values.password } : {}),
          }),
        });
      } else {
        await api<User>("/users", {
          method: "POST",
          body: JSON.stringify(values),
        });
      }
      setModalOpen(false);
      form.resetFields();
      await load();
      onSuccess(editing ? "账号已更新" : "账号已创建");
    } catch (error) {
      onError(error);
    } finally {
      setPending(false);
    }
  };

  return (
    <Space orientation="vertical" size={16} className="full-width">
      <Card
        title="账号与权限"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建账号
            </Button>
          </Space>
        }
      >
        <Table<User>
          rowKey="id"
          pagination={false}
          dataSource={users}
          columns={[
            { title: "用户名", dataIndex: "username" },
            {
              title: "角色",
              dataIndex: "role",
              render: (role: User["role"]) => <Tag>{ROLE_LABELS[role]}</Tag>,
            },
            {
              title: "状态",
              dataIndex: "is_active",
              render: (active: boolean) => (
                <Tag color={active ? "green" : "default"}>{active ? "启用" : "停用"}</Tag>
              ),
            },
            {
              title: "操作",
              render: (_, user) => (
                <Button type="link" onClick={() => openEdit(user)}>
                  {user.id === currentUserId ? "修改当前账号" : "编辑"}
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title={`最近审计记录（共 ${auditTotal} 条）`}>
        <Table<AuditLog>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={auditLogs}
          scroll={{ x: 900 }}
          columns={[
            {
              title: "时间",
              dataIndex: "createdAt",
              width: 190,
              render: (value: string) => new Date(value).toLocaleString(),
            },
            {
              title: "账号",
              dataIndex: "actorUserId",
              width: 140,
              render: (value: string | null) =>
                value ? (userById.get(value)?.username ?? value.slice(0, 8)) : "匿名",
            },
            { title: "动作", dataIndex: "action", width: 130 },
            {
              title: "结果",
              dataIndex: "outcome",
              width: 100,
              render: (value: AuditLog["outcome"]) => (
                <Tag color={value === "SUCCESS" ? "green" : "red"}>{value}</Tag>
              ),
            },
            { title: "资源", dataIndex: "resourceType", width: 140 },
            { title: "IP", dataIndex: "ipAddress", width: 140 },
            { title: "请求 ID", dataIndex: "requestId", ellipsis: true },
          ]}
        />
      </Card>

      <Modal
        title={editing ? `编辑账号 · ${editing.username}` : "新建账号"}
        open={modalOpen}
        confirmLoading={pending}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form<UserFormValues> form={form} layout="vertical" onFinish={(values) => void save(values)}>
          <Form.Item label="用户名" name="username" rules={[{ required: true }]}>
            <Input disabled={Boolean(editing)} autoComplete="off" />
          </Form.Item>
          <Form.Item
            label={editing ? "新密码（留空则不修改）" : "密码"}
            name="password"
            rules={editing ? [{ min: 10 }] : [{ required: true, min: 10 }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true }]}>
            <Select
              disabled={editing?.id === currentUserId}
              options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item label="启用" name="isActive" valuePropName="checked">
            <Switch disabled={editing?.id === currentUserId} />
          </Form.Item>
          {editing?.id === currentUserId ? (
            <Typography.Text type="secondary">当前账号不能在此停用或变更角色。</Typography.Text>
          ) : null}
        </Form>
      </Modal>
    </Space>
  );
}
