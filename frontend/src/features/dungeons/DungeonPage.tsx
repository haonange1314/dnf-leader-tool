import {
  CheckCircleOutlined,
  CopyOutlined,
  EditOutlined,
  EyeOutlined,
  HistoryOutlined,
  PauseCircleOutlined,
  PlusOutlined,
  RocketOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Switch,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { api, type Dungeon, type DungeonVersion, type User } from "../../api/client";
import {
  DungeonVersionEditor,
  type VersionEditorMode,
} from "./DungeonVersionEditor";

interface Props {
  userRole: User["role"];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

interface DungeonFormValues {
  code: string;
  name: string;
  description?: string;
  isActive: boolean;
}

interface VersionEditorState {
  dungeon: Dungeon;
  sourceVersion: DungeonVersion | null;
  mode: VersionEditorMode;
}

const statusColor = {
  DRAFT: "gold",
  PUBLISHED: "green",
  RETIRED: "default",
} as const;
const statusLabel = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
  RETIRED: "已退役",
} as const;

export function DungeonPage({ userRole, onError, onSuccess }: Props) {
  const canEdit = userRole !== "VIEWER";
  const [items, setItems] = useState<Dungeon[]>([]);
  const [loading, setLoading] = useState(true);
  const [dungeonModalOpen, setDungeonModalOpen] = useState(false);
  const [editingDungeon, setEditingDungeon] = useState<Dungeon | null>(null);
  const [versionEditor, setVersionEditor] = useState<VersionEditorState | null>(null);
  const [historyDungeon, setHistoryDungeon] = useState<Dungeon | null>(null);
  const [form] = Form.useForm<DungeonFormValues>();

  const load = async () => {
    setLoading(true);
    try {
      setItems((await api<{ items: Dungeon[] }>("/dungeons")).items);
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openCreateDungeon = () => {
    setEditingDungeon(null);
    form.resetFields();
    form.setFieldsValue({ isActive: true });
    setDungeonModalOpen(true);
  };

  const openEditDungeon = (dungeon: Dungeon) => {
    setEditingDungeon(dungeon);
    form.setFieldsValue({
      code: dungeon.code,
      name: dungeon.name,
      description: dungeon.description ?? undefined,
      isActive: dungeon.isActive,
    });
    setDungeonModalOpen(true);
  };

  const saveDungeon = async (values: DungeonFormValues) => {
    try {
      if (editingDungeon) {
        await api(`/dungeons/${editingDungeon.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: values.name.trim(),
            description: values.description?.trim() || null,
            isActive: values.isActive,
          }),
        });
        onSuccess("副本基础信息已保存");
        setDungeonModalOpen(false);
        await load();
        return;
      }
      const created = await api<Dungeon>("/dungeons", {
        method: "POST",
        body: JSON.stringify({
          code: values.code.trim().toUpperCase(),
          name: values.name.trim(),
          description: values.description?.trim() || null,
          isActive: values.isActive,
        }),
      });
      onSuccess("副本已创建，请继续配置首个草稿");
      setDungeonModalOpen(false);
      await load();
      setVersionEditor({ dungeon: created, sourceVersion: null, mode: "create" });
    } catch (error) {
      onError(error);
    }
  };

  const refreshAfterVersionChange = async (message: string) => {
    onSuccess(message);
    const refreshedItems = (await api<{ items: Dungeon[] }>("/dungeons")).items;
    setItems(refreshedItems);
    if (historyDungeon) {
      setHistoryDungeon(
        refreshedItems.find((item) => item.id === historyDungeon.id) ?? null,
      );
    }
  };

  const validateVersion = async (version: DungeonVersion) => {
    try {
      const result = await api<{ valid: boolean; issues: string[] }>(
        `/dungeon-versions/${version.id}/validate`,
        { method: "POST" },
      );
      if (result.valid) {
        Modal.success({ title: `v${version.versionNo} 校验通过`, content: "可以安全发布。" });
      } else {
        Modal.warning({
          title: `v${version.versionNo} 还有规则问题`,
          content: (
            <ul className="compact-issue-list">
              {result.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          ),
        });
      }
    } catch (error) {
      onError(error);
    }
  };

  const publishVersion = async (version: DungeonVersion) => {
    try {
      await api(`/dungeon-versions/${version.id}/publish`, { method: "POST" });
      await refreshAfterVersionChange(`v${version.versionNo} 已发布`);
    } catch (error) {
      onError(error);
    }
  };

  const retireVersion = async (version: DungeonVersion) => {
    try {
      await api(`/dungeon-versions/${version.id}/retire`, { method: "POST" });
      await refreshAfterVersionChange(`v${version.versionNo} 已退役`);
    } catch (error) {
      onError(error);
    }
  };

  const openVersion = (
    dungeon: Dungeon,
    sourceVersion: DungeonVersion | null,
    mode: VersionEditorMode,
  ) => {
    setVersionEditor({ dungeon, sourceVersion, mode });
  };

  return (
    <section>
      <div className="section-heading">
        <div>
          <Typography.Title level={2}>副本管理</Typography.Title>
          <Typography.Text type="secondary">
            维护副本主体，并通过不可变版本配置队伍、组成和自动排表规则
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!canEdit}
          onClick={openCreateDungeon}
        >
          新建副本
        </Button>
      </div>
      {items.length === 0 && !loading ? (
        <Empty description="还没有副本" />
      ) : (
        <Row gutter={[12, 12]}>
          {items.map((dungeon) => {
            const latest = dungeon.versions[0];
            return (
              <Col xs={24} xl={12} key={dungeon.id}>
                <Card
                  loading={loading}
                  className="module-card dungeon-card"
                  title={
                    <Space size={6} wrap>
                      <span className="code-badge">{dungeon.code}</span>
                      <span>{dungeon.name}</span>
                    </Space>
                  }
                  extra={
                    <Space size={4}>
                      <Tag color={dungeon.isActive ? "green" : "default"}>
                        {dungeon.isActive ? "启用" : "停用"}
                      </Tag>
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        disabled={!canEdit}
                        aria-label={`编辑副本 ${dungeon.name}`}
                        onClick={() => openEditDungeon(dungeon)}
                      />
                    </Space>
                  }
                >
                  <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>
                    {dungeon.description || "暂无说明"}
                  </Typography.Paragraph>
                  {latest ? (
                    <>
                      <Row gutter={12} className="dungeon-statistics">
                        <Col span={8}>
                          <Statistic title="最新版本" value={`v${latest.versionNo}`} />
                        </Col>
                        <Col span={8}>
                          <Statistic title="默认波数" value={latest.defaultWaveCount} />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="每波人数"
                            value={latest.teams.reduce(
                              (sum, team) => sum + team.memberCount,
                              0,
                            )}
                          />
                        </Col>
                      </Row>
                      <div className="version-row dungeon-version-row">
                        <Space wrap size={[4, 4]}>
                          <Tag color={statusColor[latest.status]}>
                            {statusLabel[latest.status]}
                          </Tag>
                          {latest.teams.map((team) => (
                            <Tag key={team.teamKey} color={team.displayColor}>
                              {team.displayName} · {team.memberCount}
                            </Tag>
                          ))}
                        </Space>
                        <Space wrap size={4}>
                          <Button
                            size="small"
                            icon={
                              latest.status === "DRAFT" ? (
                                <SettingOutlined />
                              ) : (
                                <EyeOutlined />
                              )
                            }
                            onClick={() =>
                              openVersion(
                                dungeon,
                                latest,
                                latest.status === "DRAFT" && canEdit ? "edit" : "view",
                              )
                            }
                          >
                            {latest.status === "DRAFT" && canEdit ? "编辑草稿" : "查看规则"}
                          </Button>
                          {latest.status === "DRAFT" ? (
                            <>
                              <Button
                                size="small"
                                icon={<CheckCircleOutlined />}
                                onClick={() => void validateVersion(latest)}
                              >
                                校验
                              </Button>
                              <Popconfirm
                                title={`确认发布 v${latest.versionNo}？`}
                                description="发布后该版本不可修改。"
                                okText="发布"
                                cancelText="取消"
                                disabled={!canEdit}
                                onConfirm={() => void publishVersion(latest)}
                              >
                                <Button
                                  size="small"
                                  type="primary"
                                  icon={<RocketOutlined />}
                                  disabled={!canEdit}
                                >
                                  发布
                                </Button>
                              </Popconfirm>
                            </>
                          ) : (
                            <Button
                              size="small"
                              icon={<CopyOutlined />}
                              disabled={!canEdit}
                              onClick={() => openVersion(dungeon, latest, "create")}
                            >
                              复制草稿
                            </Button>
                          )}
                        </Space>
                      </div>
                    </>
                  ) : (
                    <div className="dungeon-empty-version">
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="尚无规则版本"
                      >
                        <Button
                          type="primary"
                          icon={<SettingOutlined />}
                          disabled={!canEdit}
                          onClick={() => openVersion(dungeon, null, "create")}
                        >
                          创建首个草稿
                        </Button>
                      </Empty>
                    </div>
                  )}
                  <Button
                    type="link"
                    size="small"
                    className="dungeon-history-button"
                    icon={<HistoryOutlined />}
                    disabled={!latest}
                    onClick={() => setHistoryDungeon(dungeon)}
                  >
                    版本历史（{dungeon.versions.length}）
                  </Button>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}

      <Modal
        title={editingDungeon ? "编辑副本" : "新建副本"}
        open={dungeonModalOpen}
        onCancel={() => setDungeonModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ isActive: true }}
          onFinish={(values) => void saveDungeon(values)}
        >
          <Form.Item
            label="副本编码"
            name="code"
            rules={[
              { required: true, message: "请填写副本编码" },
              {
                pattern: /^[A-Za-z][A-Za-z0-9_]*$/,
                message: "使用字母、数字和下划线",
              },
            ]}
          >
            <Input placeholder="RAID_CUSTOM" disabled={Boolean(editingDungeon)} />
          </Form.Item>
          <Form.Item
            label="副本名称"
            name="name"
            rules={[
              { required: true, message: "请填写副本名称" },
              {
                validator: async (_, value: string) => {
                  if (!value?.trim()) throw new Error("副本名称不能为空");
                },
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <Input.TextArea rows={3} maxLength={2000} showCount />
          </Form.Item>
          <Form.Item label="启用" name="isActive" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`${historyDungeon?.name ?? "副本"} · 版本历史`}
        open={Boolean(historyDungeon)}
        onCancel={() => setHistoryDungeon(null)}
        footer={<Button onClick={() => setHistoryDungeon(null)}>关闭</Button>}
        width={860}
        destroyOnHidden
      >
        <List
          dataSource={historyDungeon?.versions ?? []}
          locale={{ emptyText: "尚无版本" }}
          renderItem={(version) => (
            <List.Item
              actions={[
                <Button
                  key="view"
                  type="link"
                  size="small"
                  onClick={() =>
                    historyDungeon &&
                    openVersion(
                      historyDungeon,
                      version,
                      version.status === "DRAFT" && canEdit ? "edit" : "view",
                    )
                  }
                >
                  {version.status === "DRAFT" && canEdit ? "编辑" : "查看"}
                </Button>,
                <Button
                  key="validate"
                  type="link"
                  size="small"
                  onClick={() => void validateVersion(version)}
                >
                  校验
                </Button>,
                ...(version.status === "DRAFT"
                  ? [
                      <Popconfirm
                        key="publish"
                        title={`确认发布 v${version.versionNo}？`}
                        description="发布后该版本不可修改。"
                        disabled={!canEdit}
                        onConfirm={() => void publishVersion(version)}
                      >
                        <Button type="link" size="small" disabled={!canEdit}>
                          发布
                        </Button>
                      </Popconfirm>,
                    ]
                  : [
                      <Button
                        key="clone"
                        type="link"
                        size="small"
                        disabled={!canEdit}
                        onClick={() =>
                          historyDungeon && openVersion(historyDungeon, version, "create")
                        }
                      >
                        复制草稿
                      </Button>,
                    ]),
                ...(version.status === "PUBLISHED"
                  ? [
                      <Popconfirm
                        key="retire"
                        title={`确认退役 v${version.versionNo}？`}
                        description="已有排表不受影响，但新排表将不能再选择该版本。"
                        disabled={!canEdit}
                        onConfirm={() => void retireVersion(version)}
                      >
                        <Button
                          danger
                          type="link"
                          size="small"
                          icon={<PauseCircleOutlined />}
                          disabled={!canEdit}
                        >
                          退役
                        </Button>
                      </Popconfirm>,
                    ]
                  : []),
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Typography.Text strong>v{version.versionNo}</Typography.Text>
                    <Tag color={statusColor[version.status]}>{statusLabel[version.status]}</Tag>
                    <Typography.Text type="secondary">
                      {version.defaultWaveCount} 波 · 每波{" "}
                      {version.teams.reduce((sum, team) => sum + team.memberCount, 0)} 人
                    </Typography.Text>
                  </Space>
                }
                description={
                  <Space wrap size={[4, 4]}>
                    {version.teams.map((team) => (
                      <Tag key={team.teamKey} color={team.displayColor}>
                        {team.displayName} · {team.memberCount}
                      </Tag>
                    ))}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Modal>

      <DungeonVersionEditor
        open={Boolean(versionEditor)}
        dungeon={versionEditor?.dungeon ?? null}
        sourceVersion={versionEditor?.sourceVersion ?? null}
        mode={versionEditor?.mode ?? "view"}
        onClose={() => setVersionEditor(null)}
        onError={onError}
        onSaved={refreshAfterVersionChange}
      />
    </section>
  );
}
