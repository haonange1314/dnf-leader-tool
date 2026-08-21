import { CopyOutlined, PlusOutlined, RocketOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Space,
  Statistic,
  Switch,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { api, type Dungeon, type DungeonVersion, type User } from "../../api/client";

interface Props {
  userRole: User["role"];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}
const statusColor = {
  DRAFT: "gold",
  PUBLISHED: "green",
  RETIRED: "default",
} as const;

export function DungeonPage({ userRole, onError, onSuccess }: Props) {
  const canEdit = userRole !== "VIEWER";
  const [items, setItems] = useState<Dungeon[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
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
  const create = async (values: Record<string, unknown>) => {
    try {
      await api("/dungeons", { method: "POST", body: JSON.stringify(values) });
      setOpen(false);
      form.resetFields();
      onSuccess("副本已创建");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const clone = async (dungeon: Dungeon, version: DungeonVersion) => {
    const payload = {
      defaultWaveCount: version.defaultWaveCount,
      minWaveCount: version.minWaveCount,
      maxWaveCount: version.maxWaveCount,
      formula: version.formula,
      teams: version.teams.map(({ id: _id, ...team }) => team),
      compositionRules: version.compositionRules,
      specialRoleRules: version.specialRoleRules,
      strengthOrderRules: version.strengthOrderRules,
      optimizationRules: version.optimizationRules,
      missingSlotPolicy: version.missingSlotPolicy,
    };
    try {
      await api(`/dungeons/${dungeon.id}/versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onSuccess("已复制为新草稿");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const publish = async (version: DungeonVersion) => {
    try {
      await api(`/dungeon-versions/${version.id}/publish`, { method: "POST" });
      onSuccess("副本版本已发布");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  return (
    <section>
      <div className="section-heading">
        <div>
          <Typography.Title level={2}>副本管理</Typography.Title>
          <Typography.Text type="secondary">
            版本化维护队伍容量、组成与优化规则
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!canEdit}
          onClick={() => setOpen(true)}
        >
          新建副本
        </Button>
      </div>
      {items.length === 0 && !loading ? (
        <Empty />
      ) : (
        <Row gutter={[16, 16]}>
          {items.map((dungeon) => {
            const latest = dungeon.versions[0];
            return (
              <Col xs={24} xl={12} key={dungeon.id}>
                <Card
                  loading={loading}
                  className="module-card"
                  title={
                    <Space>
                      <span className="code-badge">{dungeon.code}</span>
                      {dungeon.name}
                    </Space>
                  }
                  extra={
                    <Tag color={dungeon.isActive ? "green" : "default"}>
                      {dungeon.isActive ? "启用" : "停用"}
                    </Tag>
                  }
                >
                  <Typography.Paragraph type="secondary">
                    {dungeon.description || "暂无说明"}
                  </Typography.Paragraph>
                  {latest ? (
                    <>
                      <Row gutter={12}>
                        <Col span={8}>
                          <Statistic
                            title="最新版本"
                            value={`v${latest.versionNo}`}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="默认波数"
                            value={latest.defaultWaveCount}
                          />
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
                      <div className="version-row">
                        <Space wrap>
                          <Tag color={statusColor[latest.status]}>
                            {latest.status}
                          </Tag>
                          {latest.teams.map((team) => (
                            <Tag key={team.teamKey} color={team.displayColor}>
                              {team.displayName} · {team.memberCount}
                            </Tag>
                          ))}
                        </Space>
                        <Space>
                          <Button
                            icon={<CopyOutlined />}
                            disabled={!canEdit}
                            onClick={() => clone(dungeon, latest)}
                          >
                            复制草稿
                          </Button>
                          {latest.status === "DRAFT" && (
                            <Button
                              type="primary"
                              icon={<RocketOutlined />}
                              disabled={!canEdit}
                              onClick={() => publish(latest)}
                            >
                              发布
                            </Button>
                          )}
                        </Space>
                      </div>
                    </>
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="尚无版本"
                    />
                  )}
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
      <Modal
        title="新建副本"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={create}
          initialValues={{ isActive: true }}
        >
          <Form.Item
            label="副本编码"
            name="code"
            rules={[
              { required: true },
              {
                pattern: /^[A-Z][A-Z0-9_]*$/,
                message: "使用大写字母、数字和下划线",
              },
            ]}
          >
            <Input placeholder="RAID_CUSTOM" />
          </Form.Item>
          <Form.Item label="副本名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="启用" name="isActive" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
