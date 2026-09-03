import { PlusOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { api, type Permission, type Role } from "../../api/client";

interface Props {
  permissions: string[];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

interface RoleFormValues {
  code: string;
  name: string;
  description?: string;
  permissionCodes: string[];
  isActive: boolean;
}

const PERMISSION_DEPENDENCIES: Record<string, string[]> = {
  DUNGEON_WRITE: ["DUNGEON_READ"],
  ROSTER_WRITE: ["ROSTER_READ"],
  ROSTER_IMPORT: ["ROSTER_READ"],
  SCHEDULE_WRITE: ["SCHEDULE_READ"],
  SCHEDULE_GENERATE: ["SCHEDULE_READ", "SCHEDULE_WRITE"],
  SCHEDULE_PUBLISH: ["SCHEDULE_READ", "SCHEDULE_WRITE"],
  SCHEDULE_EXPORT: ["SCHEDULE_READ"],
  SHARE_MANAGE: ["SCHEDULE_READ"],
  USER_WRITE: ["USER_READ", "ROLE_READ"],
  ROLE_WRITE: ["ROLE_READ"],
};

function withPermissionDependencies(values: Array<string | number>): string[] {
  const selected = new Set(values.map(String));
  let changed = true;
  while (changed) {
    changed = false;
    [...selected].forEach((code) => {
      (PERMISSION_DEPENDENCIES[code] ?? []).forEach((dependency) => {
        if (!selected.has(dependency)) {
          selected.add(dependency);
          changed = true;
        }
      });
    });
  }
  return [...selected];
}

export function RolePage({ permissions: userPermissions, onError, onSuccess }: Props) {
  const canWrite = userPermissions.includes("ROLE_WRITE");
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<RoleFormValues>();

  const permissionGroups = useMemo(() => {
    const groups = new Map<string, Permission[]>();
    permissions.forEach((permission) => {
      groups.set(permission.module, [...(groups.get(permission.module) ?? []), permission]);
    });
    return [...groups.entries()];
  }, [permissions]);

  const load = async () => {
    setLoading(true);
    try {
      const [roleResult, permissionResult] = await Promise.all([
        api<{ items: Role[]; total: number }>("/roles"),
        api<{ items: Permission[]; total: number }>("/permissions"),
      ]);
      setRoles(roleResult.items);
      setPermissions(permissionResult.items);
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({ code: "", name: "", description: "", permissionCodes: [], isActive: true });
    setModalOpen(true);
  };

  const openEdit = (role: Role) => {
    setEditing(role);
    form.setFieldsValue({
      code: role.code,
      name: role.name,
      description: role.description ?? "",
      permissionCodes: role.permissionCodes,
      isActive: role.isActive,
    });
    setModalOpen(true);
  };

  const save = async (values: RoleFormValues) => {
    setPending(true);
    try {
      if (editing) {
        await api(`/roles/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: values.name,
            description: values.description ?? "",
            permissionCodes: values.permissionCodes,
            isActive: values.isActive,
          }),
        });
      } else {
        await api("/roles", { method: "POST", body: JSON.stringify(values) });
      }
      setModalOpen(false);
      await load();
      onSuccess(editing ? "角色权限已更新，关联账号需重新登录" : "角色已创建");
    } catch (error) {
      onError(error);
    } finally {
      setPending(false);
    }
  };

  return (
    <section>
      <div className="section-heading">
        <div>
          <Typography.Title level={2}>角色与权限</Typography.Title>
          <Typography.Text type="secondary">通过角色统一授权，权限变更即时在服务端生效</Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
          {canWrite ? <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建角色</Button> : null}
        </Space>
      </div>
      <Alert
        className="admin-security-alert"
        type="info"
        showIcon
        title="系统所有者始终拥有全部权限"
        description="修改角色权限会撤销该角色账号的旧会话，避免浏览器继续使用过期授权；停用角色前必须先迁移关联的启用账号。"
      />
      <Card className="module-card" size="small">
        <Table<Role>
          rowKey="id"
          size="small"
          loading={loading}
          pagination={false}
          dataSource={roles}
          scroll={{ x: 900 }}
          columns={[
            {
              title: "角色",
              width: 230,
              render: (_, role) => <Space><SafetyCertificateOutlined /><div><Typography.Text strong>{role.name}</Typography.Text><br /><Typography.Text type="secondary">{role.code}</Typography.Text></div></Space>,
            },
            { title: "类型", width: 100, render: (_, role) => <Tag color={role.isSystem ? "purple" : "blue"}>{role.isSystem ? "系统内置" : "自定义"}</Tag> },
            { title: "账号数", dataIndex: "userCount", width: 90, align: "center" },
            { title: "权限", render: (_, role) => <Space wrap size={[4, 4]}>{role.permissionCodes.slice(0, 6).map((code) => <Tag key={code}>{permissions.find((item) => item.code === code)?.name ?? code}</Tag>)}{role.permissionCodes.length > 6 ? <Tag>+{role.permissionCodes.length - 6}</Tag> : null}</Space> },
            { title: "状态", width: 90, render: (_, role) => <Tag color={role.isActive ? "green" : "default"}>{role.isActive ? "启用" : "停用"}</Tag> },
            { title: "操作", fixed: "right", width: 90, render: (_, role) => canWrite ? <Button type="link" onClick={() => openEdit(role)}>配置</Button> : "—" },
          ]}
        />
      </Card>

      <Modal
        title={editing ? `配置角色 · ${editing.name}` : "新建角色"}
        open={modalOpen}
        width={760}
        confirmLoading={pending}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<RoleFormValues> form={form} layout="vertical" onFinish={(values) => void save(values)}>
          <Row gutter={12}>
            <Col span={10}><Form.Item label="角色编码" name="code" rules={[{ required: true }, { pattern: /^[A-Za-z][A-Za-z0-9_-]*$/, message: "使用字母、数字、下划线或短横线" }]}><Input disabled={Boolean(editing)} placeholder="例如 RAID_OPERATOR" /></Form.Item></Col>
            <Col span={14}><Form.Item label="角色名称" name="name" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col>
          </Row>
          <Form.Item label="说明" name="description"><Input.TextArea rows={2} maxLength={500} /></Form.Item>
          <Form.Item label="启用角色" name="isActive" valuePropName="checked"><Switch disabled={editing?.code === "OWNER"} /></Form.Item>
          <Form.Item label="权限" name="permissionCodes">
            <Checkbox.Group
              className="permission-group"
              disabled={editing?.code === "OWNER"}
              onChange={(values) => form.setFieldValue("permissionCodes", withPermissionDependencies(values))}
            >
              {permissionGroups.map(([module, items]) => (
                <div key={module} className="permission-module">
                  <Typography.Text strong>{module}</Typography.Text>
                  <div className="permission-options">
                    {items.map((permission) => (
                      <Checkbox key={permission.code} value={permission.code} title={permission.description ?? undefined}>{permission.name}</Checkbox>
                    ))}
                  </div>
                </div>
              ))}
            </Checkbox.Group>
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
