import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { api, type Dungeon, type DungeonVersion } from "../../api/client";
import {
  DEFAULT_FORMULA,
  defaultDungeonVersionForm,
  dungeonVersionFormToInput,
  dungeonVersionToForm,
  type DungeonVersionFormValues,
  versionFormWarnings,
} from "./dungeonVersionForm";

export type VersionEditorMode = "create" | "edit" | "view";

interface Props {
  open: boolean;
  dungeon: Dungeon | null;
  sourceVersion: DungeonVersion | null;
  mode: VersionEditorMode;
  onClose: () => void;
  onError: (error: unknown) => void;
  onSaved: (message: string) => Promise<void>;
}

const roleMetricOptions = [
  { label: "C 强度", value: "DAMAGE" },
  { label: "奶强度", value: "BUFFER" },
];

export function DungeonVersionEditor({
  open,
  dungeon,
  sourceVersion,
  mode,
  onClose,
  onError,
  onSaved,
}: Props) {
  const [form] = Form.useForm<DungeonVersionFormValues>();
  const [saving, setSaving] = useState(false);
  const watchedTeams = Form.useWatch("teams", form) ?? [];
  const watchedDefaultWaveCount = Form.useWatch("defaultWaveCount", form) ?? 0;
  const watchedValues = Form.useWatch([], form) as DungeonVersionFormValues | undefined;
  const readOnly = mode === "view";
  const formula = sourceVersion?.formula ?? DEFAULT_FORMULA;
  const teamOptions = watchedTeams
    .filter((team) => team?.teamKey && team?.displayName)
    .map((team) => ({
      label: team.displayName,
      value: team.teamKey.trim().toUpperCase(),
    }));
  const participantsPerWave = watchedTeams.reduce(
    (sum, team) => sum + Number(team?.memberCount || 0),
    0,
  );
  const warnings = useMemo(
    () =>
      watchedValues?.teams && watchedValues.compositions
        ? versionFormWarnings(watchedValues)
        : [],
    [watchedValues],
  );

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue(
      sourceVersion ? dungeonVersionToForm(sourceVersion) : defaultDungeonVersionForm(),
    );
  }, [form, open, sourceVersion]);

  const save = async () => {
    if (!dungeon || readOnly) return;
    try {
      const values = await form.validateFields();
      const formIssues = versionFormWarnings(values);
      if (formIssues.length) {
        Modal.warning({
          title: "请先修正规则",
          content: (
            <ul className="compact-issue-list">
              {formIssues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          ),
        });
        return;
      }
      setSaving(true);
      const payload = dungeonVersionFormToInput(values, formula);
      if (mode === "edit" && sourceVersion) {
        await api(`/dungeon-versions/${sourceVersion.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        await onSaved(`v${sourceVersion.versionNo} 草稿已保存`);
      } else {
        await api(`/dungeons/${dungeon.id}/versions`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await onSaved(sourceVersion ? "已复制并保存为新草稿" : "首个副本草稿已创建");
      }
      onClose();
    } catch (error) {
      onError(error);
    } finally {
      setSaving(false);
    }
  };

  const title = readOnly
    ? `${dungeon?.name ?? "副本"} · v${sourceVersion?.versionNo ?? "-"}`
    : mode === "edit"
      ? `编辑 ${dungeon?.name ?? "副本"} · v${sourceVersion?.versionNo ?? "-"} 草稿`
      : sourceVersion
        ? `基于 v${sourceVersion.versionNo} 创建新草稿`
        : `创建 ${dungeon?.name ?? "副本"} 的首个草稿`;

  return (
    <Drawer
      className="dungeon-version-editor"
      title={title}
      size="min(1180px, 96vw)"
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>{readOnly ? "关闭" : "取消"}</Button>
          {!readOnly && (
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={() => void save()}
            >
              保存草稿
            </Button>
          )}
        </Space>
      }
    >
      <div className="dungeon-editor-summary">
        <Statistic title="默认波数" value={watchedDefaultWaveCount} />
        <Statistic title="队伍数量" value={watchedTeams.length} />
        <Statistic title="每波人数" value={participantsPerWave} />
        <div className="dungeon-formula-summary">
          <Typography.Text type="secondary">评分公式</Typography.Text>
          <Typography.Text strong>
            {formula.code} v{formula.version}
          </Typography.Text>
          <Typography.Text type="secondary">
            C × {formula.damageScale} · 奶 × {formula.bufferScale}
          </Typography.Text>
        </div>
      </div>
      {warnings.length > 0 && !readOnly && (
        <Alert
          className="dungeon-editor-alert"
          type="warning"
          showIcon
          message={`还有 ${warnings.length} 项规则需要修正`}
          description={warnings.join("；")}
        />
      )}
      <Form
        form={form}
        layout="vertical"
        disabled={readOnly}
        initialValues={defaultDungeonVersionForm()}
      >
        <Tabs
          items={[
            {
              key: "structure",
              label: "波次与队伍",
              forceRender: true,
              children: (
                <StructureFields teamOptions={teamOptions} readOnly={readOnly} />
              ),
            },
            {
              key: "composition",
              label: "队伍组成",
              forceRender: true,
              children: (
                <CompositionFields teamOptions={teamOptions} readOnly={readOnly} />
              ),
            },
            {
              key: "rules",
              label: "自动排表规则",
              forceRender: true,
              children: (
                <OptimizationFields teamOptions={teamOptions} readOnly={readOnly} />
              ),
            },
          ]}
        />
      </Form>
    </Drawer>
  );
}

function StructureFields({
  teamOptions,
  readOnly,
}: {
  teamOptions: Array<{ label: string; value: string }>;
  readOnly: boolean;
}) {
  return (
    <>
      <Card size="small" title="波数范围" className="dungeon-editor-section">
        <Row gutter={12}>
          <Col xs={24} md={8}>
            <Form.Item
              label="默认波数"
              name="defaultWaveCount"
              rules={[{ required: true, message: "请填写默认波数" }]}
            >
              <InputNumber min={1} max={50} className="full-width" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item
              label="最少波数"
              name="minWaveCount"
              rules={[{ required: true, message: "请填写最少波数" }]}
            >
              <InputNumber min={1} max={50} className="full-width" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="最多波数" name="maxWaveCount">
              <InputNumber
                min={1}
                max={50}
                placeholder="不限制"
                className="full-width"
              />
            </Form.Item>
          </Col>
        </Row>
      </Card>
      <Form.List name="teams">
        {(fields, { add, remove, move }) => (
          <Card
            size="small"
            title="队伍配置"
            className="dungeon-editor-section"
            extra={
              !readOnly && (
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      teamKey: `TEAM_${fields.length + 1}`,
                      displayName: `队伍 ${fields.length + 1}`,
                      displayColor: "#3e63dd",
                      memberCount: 4,
                      strengthRank: fields.length + 1,
                    })
                  }
                >
                  添加队伍
                </Button>
              )
            }
          >
            {fields.map((field, index) => (
              <div className="dungeon-team-row" key={field.key}>
                <div className="dungeon-team-order">
                  <Tag>{index + 1}</Tag>
                  {!readOnly && (
                    <Space size={0} orientation="vertical">
                      <Button
                        type="text"
                        size="small"
                        icon={<ArrowUpOutlined />}
                        disabled={index === 0}
                        aria-label={`上移队伍 ${index + 1}`}
                        onClick={() => move(index, index - 1)}
                      />
                      <Button
                        type="text"
                        size="small"
                        icon={<ArrowDownOutlined />}
                        disabled={index === fields.length - 1}
                        aria-label={`下移队伍 ${index + 1}`}
                        onClick={() => move(index, index + 1)}
                      />
                    </Space>
                  )}
                </div>
                <Row gutter={10} className="dungeon-team-fields">
                  <Col xs={24} md={5}>
                    <Form.Item
                      label="队伍标识"
                      name={[field.name, "teamKey"]}
                      rules={[
                        { required: true, message: "请填写标识" },
                        {
                          pattern: /^[A-Za-z][A-Za-z0-9_]*$/,
                          message: "使用字母、数字和下划线",
                        },
                      ]}
                    >
                      <Input placeholder="RED" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item
                      label="显示名称"
                      name={[field.name, "displayName"]}
                      rules={[{ required: true, message: "请填写名称" }]}
                    >
                      <Input placeholder="红队" />
                    </Form.Item>
                  </Col>
                  <Col xs={12} md={4}>
                    <Form.Item
                      label="颜色"
                      name={[field.name, "displayColor"]}
                      rules={[{ required: true }]}
                    >
                      <Input type="color" />
                    </Form.Item>
                  </Col>
                  <Col xs={12} md={4}>
                    <Form.Item
                      label="人数"
                      name={[field.name, "memberCount"]}
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={64} className="full-width" />
                    </Form.Item>
                  </Col>
                  <Col xs={18} md={4}>
                    <Form.Item
                      label="强度排名"
                      name={[field.name, "strengthRank"]}
                      tooltip="数字越小队伍越强；用于识别固定主队奶的目标队伍"
                    >
                      <InputNumber min={1} max={8} className="full-width" />
                    </Form.Item>
                  </Col>
                  <Col xs={6} md={1} className="dungeon-team-delete">
                    {!readOnly && (
                      <Button
                        danger
                        type="text"
                        icon={<DeleteOutlined />}
                        disabled={fields.length === 1}
                        aria-label={`删除队伍 ${index + 1}`}
                        onClick={() => remove(field.name)}
                      />
                    )}
                  </Col>
                </Row>
              </div>
            ))}
            {fields.length === 0 && (
              <Alert type="error" showIcon message="副本至少需要一支队伍" />
            )}
            {teamOptions.length > 0 && (
              <Typography.Text type="secondary">
                队伍显示顺序取当前列表顺序；总人数由各队人数自动相加。
              </Typography.Text>
            )}
          </Card>
        )}
      </Form.List>
    </>
  );
}

function CompositionFields({
  teamOptions,
  readOnly,
}: {
  teamOptions: Array<{ label: string; value: string }>;
  readOnly: boolean;
}) {
  return (
    <Form.List name="compositions">
      {(fields, { add, remove }) => (
        <Card
          size="small"
          title="合法队伍组成"
          className="dungeon-editor-section"
          extra={
            !readOnly && (
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={() =>
                  add({
                    code: `RULE_${fields.length + 1}`,
                    applicableTeamKeys: teamOptions.map((option) => option.value),
                    damageCount: 3,
                    bufferCount: 1,
                    priority: fields.length + 1,
                  })
                }
              >
                添加组成
              </Button>
            )
          }
        >
          <Typography.Paragraph type="secondary">
            完整队伍必须命中一条组成规则；优先级数字越小，自动排表越优先选择。
          </Typography.Paragraph>
          {fields.map((field, index) => (
            <Row gutter={10} align="bottom" key={field.key}>
              <Col xs={24} md={5}>
                <Form.Item
                  label="规则标识"
                  name={[field.name, "code"]}
                  rules={[{ required: true, message: "请填写规则标识" }]}
                >
                  <Input placeholder="3D1B" />
                </Form.Item>
              </Col>
              <Col xs={24} md={7}>
                <Form.Item
                  label="适用队伍"
                  name={[field.name, "applicableTeamKeys"]}
                  rules={[{ required: true, message: "至少选择一支队伍" }]}
                >
                  <Select mode="multiple" options={teamOptions} />
                </Form.Item>
              </Col>
              <Col xs={8} md={3}>
                <Form.Item
                  label="C 数量"
                  name={[field.name, "damageCount"]}
                  rules={[{ required: true, message: "请填写 C 数量" }]}
                >
                  <InputNumber min={0} max={64} className="full-width" />
                </Form.Item>
              </Col>
              <Col xs={8} md={3}>
                <Form.Item
                  label="奶数量"
                  name={[field.name, "bufferCount"]}
                  rules={[{ required: true, message: "请填写奶数量" }]}
                >
                  <InputNumber min={0} max={64} className="full-width" />
                </Form.Item>
              </Col>
              <Col xs={6} md={3}>
                <Form.Item
                  label="优先级"
                  name={[field.name, "priority"]}
                  rules={[{ required: true, message: "请填写优先级" }]}
                >
                  <InputNumber min={1} max={64} className="full-width" />
                </Form.Item>
              </Col>
              <Col xs={2} md={1}>
                {!readOnly && (
                  <Form.Item label=" ">
                    <Button
                      danger
                      type="text"
                      icon={<DeleteOutlined />}
                      aria-label={`删除组成 ${index + 1}`}
                      onClick={() => remove(field.name)}
                    />
                  </Form.Item>
                )}
              </Col>
            </Row>
          ))}
          {fields.length === 0 && (
            <Alert type="error" showIcon message="每支队伍必须至少配置一条合法组成" />
          )}
        </Card>
      )}
    </Form.List>
  );
}

function OptimizationFields({
  teamOptions,
  readOnly,
}: {
  teamOptions: Array<{ label: string; value: string }>;
  readOnly: boolean;
}) {
  const treasureEnabled = Form.useWatch("treasureRuleEnabled");
  return (
    <>
      <Card size="small" title="秘宝 C 规则" className="dungeon-editor-section">
        <Form.Item
          label="启用每波秘宝 C 核心"
          name="treasureRuleEnabled"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
        {treasureEnabled && (
          <Row gutter={12}>
            <Col xs={24} md={6}>
              <Form.Item label="每波数量" name="treasureCount">
                <InputNumber min={1} max={64} className="full-width" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item
                label="目标队伍"
                name="treasureTargetTeamKey"
                rules={[{ required: true, message: "请选择目标队伍" }]}
              >
                <Select options={teamOptions} />
              </Form.Item>
            </Col>
            <Col xs={12} md={5}>
              <Form.Item
                label="完整波必须满足"
                name="treasureRequired"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={12} md={5}>
              <Form.Item
                label="搭配较弱普通 C"
                name="treasureCompanionOptimization"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </Col>
          </Row>
        )}
      </Card>
      <Card size="small" title="强度与跨波优化" className="dungeon-editor-section">
        <Form.List name="strengthOrders">
          {(fields, { add, remove }) => (
            <div className="dungeon-strength-orders">
              <div className="dungeon-rule-heading">
                <div>
                  <Typography.Text strong>队内强度顺序</Typography.Text>
                  <Typography.Text type="secondary">
                    每条规则中的队伍按选择顺序从强到弱排列
                  </Typography.Text>
                </div>
                {!readOnly && (
                  <Button
                    size="small"
                    icon={<PlusOutlined />}
                    onClick={() =>
                      add({
                        metric: "DAMAGE",
                        teamKeys: teamOptions.map((option) => option.value),
                      })
                    }
                  >
                    添加顺序
                  </Button>
                )}
              </div>
              {fields.map((field, index) => (
                <Row gutter={10} align="bottom" key={field.key}>
                  <Col xs={24} md={6}>
                    <Form.Item
                      label="强度指标"
                      name={[field.name, "metric"]}
                      rules={[{ required: true, message: "请选择强度指标" }]}
                    >
                      <Select options={roleMetricOptions} />
                    </Form.Item>
                  </Col>
                  <Col xs={22} md={16}>
                    <Form.Item
                      label="队伍顺序（从强到弱）"
                      name={[field.name, "teamKeys"]}
                      rules={[{ required: true, message: "至少选择一支队伍" }]}
                    >
                      <Select mode="multiple" options={teamOptions} />
                    </Form.Item>
                  </Col>
                  <Col xs={2} md={2}>
                    {!readOnly && (
                      <Form.Item label=" ">
                        <Button
                          danger
                          type="text"
                          icon={<DeleteOutlined />}
                          aria-label={`删除强度顺序 ${index + 1}`}
                          onClick={() => remove(field.name)}
                        />
                      </Form.Item>
                    )}
                  </Col>
                </Row>
              ))}
              {fields.length === 0 && (
                <Typography.Text type="secondary">不约束队伍强度顺序</Typography.Text>
              )}
            </div>
          )}
        </Form.List>
        <Divider />
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <Form.Item label="跨波平衡指标" name="balanceMetrics">
              <Checkbox.Group options={roleMetricOptions} />
            </Form.Item>
          </Col>
        </Row>
        <Divider />
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <Form.Item
              label="考虑玩家偏好"
              name="respectPlayerPreferences"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="空位策略" name="missingSlotMode">
              <Radio.Group
                options={[
                  { label: "优先填满前面波次", value: "FILL_EARLIER_WAVES" },
                  { label: "空位均匀分散", value: "SPREAD_EVENLY" },
                ]}
              />
            </Form.Item>
          </Col>
        </Row>
      </Card>
    </>
  );
}
