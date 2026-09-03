import {
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { api, type ManagedUser, type Role } from "../../api/client";

interface Props {
  currentUserId: string;
  permissions: string[];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

interface UserFormValues {
  username: string;
  password?: string;
  roleId: string;
  isActive: boolean;
}

export function UserPage({ currentUserId, permissions, onError, onSuccess }: Props) {
  const canWrite = permissions.includes("USER_WRITE");
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>();
  const [page, setPage] = useState(1);
  const [form] = Form.useForm<UserFormValues>();

  const load = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({ limit: "20", offset: String((page - 1) * 20) });
      if (search.trim()) query.set("search", search.trim());
      if (roleFilter) query.set("roleId", roleFilter);
      if (activeFilter !== undefined) query.set("isActive", String(activeFilter));
      const [userResult, roleResult] = await Promise.all([
        api<{ items: ManagedUser[]; total: number }>(`/users?${query}`),
        permissions.includes("ROLE_READ")
          ? api<{ items: Role[]; total: number }>("/roles?includeInactive=false")
          : Promise.resolve({ items: [], total: 0 }),
      ]);
      setUsers(userResult.items);
      setTotal(userResult.total);
      setRoles(roleResult.items);
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [page, roleFilter, activeFilter]);

  const activeCount = useMemo(() => users.filter((user) => user.is_active).length, [users]);
  const sessionCount = useMemo(
    () => users.reduce((count, user) => count + user.active_session_count, 0),
    [users],
  );

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      username: "",
      password: "",
      roleId: roles.find((role) => role.code === "EDITOR")?.id ?? roles[0]?.id,
      isActive: true,
    });
    setModalOpen(true);
  };

  const openEdit = (user: ManagedUser) => {
    setEditing(user);
    form.setFieldsValue({
      username: user.username,
      password: "",
      roleId: user.role_id,
      isActive: user.is_active,
    });
    setModalOpen(true);
  };

  const save = async (values: UserFormValues) => {
    setPending(true);
    try {
      if (editing) {
        await api(`/users/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            roleId: values.roleId,
            isActive: values.isActive,
            ...(values.password ? { password: values.password } : {}),
          }),
        });
      } else {
        await api("/users", { method: "POST", body: JSON.stringify(values) });
      }
      setModalOpen(false);
      form.resetFields();
      await load();
      onSuccess(editing ? "账号已更新，相关旧会话已失效" : "账号已创建");
    } catch (error) {
      onError(error);
    } finally {
      setPending(false);
    }
  };

  const revokeSessions = async (user: ManagedUser) => {
    try {
      const result = await api<{ revokedCount: number }>(`/users/${user.id}/revoke-sessions`, {
        method: "POST",
      });
      await load();
      onSuccess(`已撤销 ${result.revokedCount} 个其他登录会话`);
    } catch (error) {
      onError(error);
    }
  };

  return (
    <section>
      <div className="section-heading">
        <div>
          <Typography.Title level={2}>用户管理</Typography.Title>
          <Typography.Text type="secondary">维护登录账号、角色归属和在线会话</Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
          {canWrite ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建账号</Button>
          ) : null}
        </Space>
      </div>

      <Row gutter={[10, 10]} className="admin-stat-row">
        <Col xs={24} sm={8}><Card size="small"><Statistic title="符合条件账号" value={total} prefix={<UserOutlined />} /></Card></Col>
        <Col xs={24} sm={8}><Card size="small"><Statistic title="本页启用账号" value={activeCount} /></Card></Col>
        <Col xs={24} sm={8}><Card size="small"><Statistic title="本页有效会话" value={sessionCount} prefix={<KeyOutlined />} /></Card></Col>
      </Row>

      <Card className="module-card" size="small">
        <Space wrap className="admin-filter-bar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索用户名"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onPressEnter={() => { setPage(1); void load(); }}
            style={{ width: 220 }}
          />
          <Button onClick={() => { setPage(1); void load(); }}>查询</Button>
          <Select
            allowClear
            placeholder="全部角色"
            value={roleFilter}
            onChange={(value) => { setPage(1); setRoleFilter(value); }}
            options={roles.map((role) => ({ value: role.id, label: role.name }))}
            style={{ width: 170 }}
          />
          <Select
            allowClear
            placeholder="全部状态"
            value={activeFilter}
            onChange={(value) => { setPage(1); setActiveFilter(value); }}
            options={[{ value: true, label: "启用" }, { value: false, label: "停用" }]}
            style={{ width: 120 }}
          />
        </Space>
        <Table<ManagedUser>
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={users}
          scroll={{ x: 980 }}
          pagination={{ current: page, pageSize: 20, total, showSizeChanger: false, onChange: setPage }}
          columns={[
            {
              title: "账号",
              dataIndex: "username",
              width: 180,
              render: (username: string, user) => (
                <Space size={5}><Typography.Text strong>{username}</Typography.Text>{user.id === currentUserId ? <Tag color="blue">当前</Tag> : null}</Space>
              ),
            },
            {
              title: "角色",
              width: 190,
              render: (_, user) => <><Tag color={user.role === "OWNER" ? "purple" : "blue"}>{user.role_name}</Tag><Typography.Text type="secondary">{user.role}</Typography.Text></>,
            },
            { title: "状态", width: 90, render: (_, user) => <Tag color={user.is_active ? "green" : "default"}>{user.is_active ? "启用" : "停用"}</Tag> },
            { title: "有效会话", dataIndex: "active_session_count", width: 90, align: "center" },
            { title: "最近登录", dataIndex: "last_login_at", width: 170, render: (value: string | null) => value ? new Date(value).toLocaleString() : "从未登录" },
            { title: "创建时间", dataIndex: "created_at", width: 170, render: (value: string) => new Date(value).toLocaleString() },
            {
              title: "操作",
              fixed: "right",
              width: 190,
              render: (_, user) => canWrite ? (
                <Space size={0}>
                  <Button type="link" onClick={() => openEdit(user)}>编辑</Button>
                  <Popconfirm title="撤销该账号的其他有效会话？" onConfirm={() => void revokeSessions(user)}>
                    <Button type="link" icon={<StopOutlined />}>下线</Button>
                  </Popconfirm>
                </Space>
              ) : "—",
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? `编辑账号 · ${editing.username}` : "新建账号"}
        open={modalOpen}
        confirmLoading={pending}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<UserFormValues> form={form} layout="vertical" onFinish={(values) => void save(values)}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, whitespace: true }]}>
            <Input disabled={Boolean(editing)} autoComplete="off" />
          </Form.Item>
          <Form.Item label={editing ? "重置密码（留空不修改）" : "初始密码"} name="password" rules={editing ? [{ min: 10 }] : [{ required: true, min: 10 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item label="角色" name="roleId" rules={[{ required: true }]}>
            <Select disabled={editing?.id === currentUserId} options={roles.map((role) => ({ value: role.id, label: `${role.name}（${role.code}）` }))} />
          </Form.Item>
          <Form.Item label="启用账号" name="isActive" valuePropName="checked">
            <Switch disabled={editing?.id === currentUserId} />
          </Form.Item>
          {editing?.id === currentUserId ? <Typography.Text type="secondary">当前账号只能在此重置密码，不能停用或变更自身角色。</Typography.Text> : null}
        </Form>
      </Modal>
    </section>
  );
}
