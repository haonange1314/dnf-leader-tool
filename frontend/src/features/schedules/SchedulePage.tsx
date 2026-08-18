import {
  CheckCircleOutlined,
  CopyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Dungeon,
  type ScheduleDetail,
  type ScheduleParticipant,
  type SchedulePreference,
  type ScheduleSummary,
  type ScheduleSyncPreview,
  type ValidationReport,
} from "../../api/client";

interface Props {
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

const ISSUE_LABELS: Record<string, string> = {
  CAPACITY_EXCEEDED: "参团角色超过排表容量",
  PARTICIPANT_SHORTAGE: "参团角色少于排表容量",
  DAMAGE_IDEAL_SHORTAGE: "C 数量不足理想组成",
  BUFFER_BASE_SHORTAGE: "奶数量不足基础组成",
  TREASURE_SHORTAGE: "秘宝 C 数量不足",
  PLAYER_WAVE_CAPACITY_INSUFFICIENT: "玩家可用波次不足",
};

export function SchedulePage({ onError, onSuccess }: Props) {
  const [schedules, setSchedules] = useState<ScheduleSummary[]>([]);
  const [dungeons, setDungeons] = useState<Dungeon[]>([]);
  const [detail, setDetail] = useState<ScheduleDetail | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [syncPreview, setSyncPreview] = useState<ScheduleSyncPreview | null>(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferenceDrafts, setPreferenceDrafts] = useState<SchedulePreference[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyName, setCopyName] = useState("");
  const [waveCount, setWaveCount] = useState(1);
  const [createForm] = Form.useForm();

  const versionOptions = useMemo(
    () =>
      dungeons.flatMap((dungeon) =>
        dungeon.versions
          .filter((version) => version.status === "PUBLISHED" && dungeon.isActive)
          .map((version) => ({
            label: `${dungeon.name} · v${version.versionNo}`,
            value: version.id,
            defaultWaveCount: version.defaultWaveCount,
          })),
      ),
    [dungeons],
  );

  const loadList = async () => {
    try {
      const [scheduleResult, dungeonResult] = await Promise.all([
        api<{ items: ScheduleSummary[] }>("/schedules"),
        api<{ items: Dungeon[] }>("/dungeons"),
      ]);
      setSchedules(scheduleResult.items);
      setDungeons(dungeonResult.items);
    } catch (error) {
      onError(error);
    }
  };

  const applyDetail = (next: ScheduleDetail) => {
    setDetail(next);
    setWaveCount(next.waveCount);
    setSelectedIds(
      next.participants.filter((participant) => participant.isSelected).map((item) => item.id),
    );
    setValidation(null);
  };

  const openSchedule = async (scheduleId: string) => {
    try {
      applyDetail(await api<ScheduleDetail>(`/schedules/${scheduleId}`));
    } catch (error) {
      onError(error);
    }
  };

  useEffect(() => {
    void loadList();
  }, []);

  const createSchedule = async (values: {
    name: string;
    dungeonVersionId: string;
    waveCount?: number;
    note?: string;
  }) => {
    try {
      const created = await api<ScheduleDetail>("/schedules", {
        method: "POST",
        body: JSON.stringify(values),
      });
      setCreateOpen(false);
      createForm.resetFields();
      await loadList();
      applyDetail(created);
      onSuccess("排表已创建");
    } catch (error) {
      onError(error);
    }
  };

  const updateWaves = async () => {
    if (!detail) return;
    try {
      const next = await api<ScheduleDetail>(`/schedules/${detail.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: detail.revision,
          waveCount,
          confirmWaveReduction: false,
        }),
      });
      applyDetail(next);
      await loadList();
      onSuccess("排表波数已更新");
    } catch (error) {
      onError(error);
    }
  };

  const saveParticipants = async () => {
    if (!detail) return;
    try {
      const next = await api<ScheduleDetail>(`/schedules/${detail.id}/participants`, {
        method: "PUT",
        body: JSON.stringify({
          baseRevision: detail.revision,
          selectedParticipantIds: selectedIds,
        }),
      });
      applyDetail(next);
      await loadList();
      onSuccess("参团角色已更新");
    } catch (error) {
      onError(error);
    }
  };

  const openPreferences = () => {
    if (!detail) return;
    setPreferenceDrafts(detail.preferences.map((preference) => ({ ...preference })));
    setPreferencesOpen(true);
  };

  const updatePreference = (
    playerId: string,
    values: Partial<SchedulePreference>,
  ) => {
    setPreferenceDrafts((current) =>
      current.map((preference) =>
        preference.playerId === playerId ? { ...preference, ...values } : preference,
      ),
    );
  };

  const savePreferences = async () => {
    if (!detail) return;
    try {
      const next = await api<ScheduleDetail>(
        `/schedules/${detail.id}/player-preferences`,
        {
          method: "PUT",
          body: JSON.stringify({
            baseRevision: detail.revision,
            preferences: preferenceDrafts,
          }),
        },
      );
      setPreferencesOpen(false);
      applyDetail(next);
      await loadList();
      onSuccess("玩家偏好已更新");
    } catch (error) {
      onError(error);
    }
  };

  const copySchedule = async () => {
    if (!detail) return;
    try {
      const copied = await api<ScheduleDetail>(`/schedules/${detail.id}/copy`, {
        method: "POST",
        body: JSON.stringify({ baseRevision: detail.revision, name: copyName }),
      });
      setCopyOpen(false);
      await loadList();
      applyDetail(copied);
      onSuccess("排表已复制，角色次数和队伍位置已重置");
    } catch (error) {
      onError(error);
    }
  };

  const validate = async () => {
    if (!detail) return;
    try {
      setValidation(
        await api<ValidationReport>(`/schedules/${detail.id}/validate`, { method: "POST" }),
      );
      await loadList();
    } catch (error) {
      onError(error);
    }
  };

  const previewSync = async () => {
    if (!detail) return;
    try {
      setSyncPreview(
        await api<ScheduleSyncPreview>(`/schedules/${detail.id}/sync-characters/preview`, {
          method: "POST",
        }),
      );
    } catch (error) {
      onError(error);
    }
  };

  const commitSync = async () => {
    if (!detail || !syncPreview) return;
    try {
      const next = await api<ScheduleDetail>(
        `/schedules/${detail.id}/sync-characters/commit`,
        {
          method: "POST",
          body: JSON.stringify({
            baseRevision: detail.revision,
            sourceFingerprint: syncPreview.sourceFingerprint,
          }),
        },
      );
      setSyncPreview(null);
      applyDetail(next);
      await loadList();
      onSuccess("人员快照已同步");
    } catch (error) {
      onError(error);
    }
  };

  if (!detail) {
    return (
      <section>
        <div className="section-heading">
          <div>
            <Typography.Title level={2}>排表管理</Typography.Title>
            <Typography.Text type="secondary">
              创建排表、选择参团角色并进行生成前预检查
            </Typography.Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建排表
          </Button>
        </div>
        {schedules.length ? (
          <Row gutter={[16, 16]}>
            {schedules.map((schedule) => (
              <Col xs={24} lg={12} xl={8} key={schedule.id}>
                <Card
                  hoverable
                  className="module-card"
                  onClick={() => void openSchedule(schedule.id)}
                >
                  <Space orientation="vertical" className="full-width">
                    <Space className="schedule-card-title">
                      <Typography.Title level={4}>{schedule.name}</Typography.Title>
                      <Tag color={schedule.status === "DRAFT" ? "orange" : "green"}>
                        {schedule.status}
                      </Tag>
                    </Space>
                    <Typography.Text type="secondary">
                      {schedule.waveCount} 波 · revision {schedule.revision}
                    </Typography.Text>
                    {schedule.validationSummary ? (
                      <Typography.Text type="secondary">
                        错误 {schedule.validationSummary.error ?? 0} · 警告{" "}
                        {schedule.validationSummary.warning ?? 0} · 提示{" "}
                        {schedule.validationSummary.info ?? 0}
                      </Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">尚未预检查</Typography.Text>
                    )}
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Empty description="还没有排表" />
        )}
        <Modal
          title="新建排表"
          open={createOpen}
          onCancel={() => setCreateOpen(false)}
          onOk={() => createForm.submit()}
          destroyOnHidden
        >
          <Form form={createForm} layout="vertical" onFinish={createSchedule}>
            <Form.Item label="排表名称" name="name" rules={[{ required: true }]}>
              <Input placeholder="例如：周六晚巴卡尔" />
            </Form.Item>
            <Form.Item label="副本版本" name="dungeonVersionId" rules={[{ required: true }]}>
              <Select
                options={versionOptions}
                onChange={(versionId) => {
                  const option = versionOptions.find((item) => item.value === versionId);
                  createForm.setFieldValue("waveCount", option?.defaultWaveCount);
                }}
              />
            </Form.Item>
            <Form.Item label="波数" name="waveCount" rules={[{ required: true }]}>
              <InputNumber min={1} max={50} className="full-width" />
            </Form.Item>
            <Form.Item label="备注" name="note">
              <Input.TextArea rows={3} />
            </Form.Item>
          </Form>
        </Modal>
      </section>
    );
  }

  const participantsById = new Map(
    detail.participants.map((participant) => [participant.id, participant]),
  );
  const selectedParticipants = detail.participants.filter((participant) => participant.isSelected);
  const damageCount = selectedParticipants.filter(
    (participant) => participant.roleTypeSnapshot === "DAMAGE",
  ).length;

  return (
    <section>
      <div className="section-heading">
        <div>
          <Button type="link" className="schedule-back" onClick={() => setDetail(null)}>
            ← 返回排表列表
          </Button>
          <Typography.Title level={2}>{detail.name}</Typography.Title>
          <Typography.Text type="secondary">
            {detail.waveCount} 波 · revision {detail.revision} · {detail.status}
          </Typography.Text>
        </div>
        <Space wrap>
          <Button
            icon={<CopyOutlined />}
            onClick={() => {
              setCopyName(`${detail.name} - 副本`);
              setCopyOpen(true);
            }}
          >
            复制排表
          </Button>
          <Button icon={<SettingOutlined />} onClick={openPreferences}>
            玩家偏好
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => void previewSync()}>
            同步角色
          </Button>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => void validate()}>
            运行预检查
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} className="schedule-summary">
        <Col xs={12} md={6}>
          <Card><Statistic title="参团角色" value={selectedParticipants.length} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="C" value={damageCount} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card><Statistic title="奶" value={selectedParticipants.length - damageCount} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Space.Compact block>
              <InputNumber min={1} max={50} value={waveCount} onChange={(value) => setWaveCount(value ?? 1)} />
              <Button icon={<SettingOutlined />} onClick={() => void updateWaves()}>更新波数</Button>
            </Space.Compact>
          </Card>
        </Col>
      </Row>

      {validation ? (
        <Card title="预检查结果" className="schedule-panel">
          <Space wrap className="validation-summary">
            <Tag color="red">错误 {validation.summary.error}</Tag>
            <Tag color="orange">警告 {validation.summary.warning}</Tag>
            <Tag color="blue">提示 {validation.summary.info}</Tag>
          </Space>
          {validation.issues.length ? (
            <div className="issue-list">
              {validation.issues.map((issue) => (
                <Alert
                  key={`${issue.code}-${JSON.stringify(issue.message_params)}`}
                  className="full-width"
                  type={issue.severity === "ERROR" ? "error" : issue.severity === "WARNING" ? "warning" : "info"}
                  title={ISSUE_LABELS[issue.code] ?? issue.code}
                  description={JSON.stringify(issue.message_params)}
                  showIcon
                />
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有问题" />
          )}
        </Card>
      ) : null}

      <Card
        title="参团角色"
        className="schedule-panel"
        extra={<Button onClick={() => void saveParticipants()}>保存选择</Button>}
      >
        <Checkbox.Group value={selectedIds} onChange={(values) => setSelectedIds(values as string[])}>
          <div className="participant-grid">
            {detail.participants.map((participant) => (
              <Checkbox value={participant.id} key={participant.id} className="participant-option">
                <ParticipantLabel participant={participant} />
              </Checkbox>
            ))}
          </div>
        </Checkbox.Group>
      </Card>

      <div className="wave-list">
        {detail.waves.map((wave) => (
          <Card title={`第 ${wave.waveNo} 波`} key={wave.id} className="schedule-panel wave-card">
            <Row gutter={[12, 12]}>
              {wave.teams.map((team) => (
                <Col xs={24} xl={Math.max(6, Math.floor(24 / wave.teams.length))} key={team.id}>
                  <Card
                    size="small"
                    title={team.displayNameSnapshot}
                    className="team-card"
                    style={{ borderTopColor: team.displayColorSnapshot }}
                  >
                    <div className="team-slots">
                      {team.slots.map((slot) => {
                        const participant = slot.participantId
                          ? participantsById.get(slot.participantId)
                          : undefined;
                        return (
                          <div className="team-slot" key={slot.id}>
                            <Typography.Text type={participant ? undefined : "secondary"}>
                              {participant ? (
                                <ParticipantLabel participant={participant} compact />
                              ) : (
                                `位置 ${slot.slotNo} · 待排`
                              )}
                            </Typography.Text>
                          </div>
                        );
                      })}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        ))}
      </div>

      <Modal
        title="复制排表"
        open={copyOpen}
        onCancel={() => setCopyOpen(false)}
        onOk={() => void copySchedule()}
        okText="创建副本"
        okButtonProps={{ disabled: !copyName.trim() }}
      >
        <Typography.Paragraph type="secondary">
          将复制副本版本、波数、参团选择和玩家偏好；角色使用最新档案数据，队伍位置与锁定状态会清空。
        </Typography.Paragraph>
        <Input
          value={copyName}
          maxLength={160}
          onChange={(event) => setCopyName(event.target.value)}
          placeholder="新排表名称"
        />
      </Modal>

      <Modal
        title="同步角色数据"
        open={syncPreview !== null}
        onCancel={() => setSyncPreview(null)}
        onOk={() => void commitSync()}
        okText="确认同步"
        okButtonProps={{ disabled: !syncPreview?.changes.length }}
      >
        {syncPreview ? (
          <>
            <Typography.Paragraph>
              新增 {syncPreview.summary.ADD} · 更新 {syncPreview.summary.UPDATE} · 停用{" "}
              {syncPreview.summary.DESELECT}
            </Typography.Paragraph>
            {syncPreview.changes.length ? (
              <div className="sync-change-list">
                {syncPreview.changes.map((change) => (
                  <Space key={`${change.action}-${change.characterId}`}>
                    <Tag>{change.action}</Tag>
                    <span>{change.playerName} · {change.characterName}</span>
                    {change.changedFields.length ? (
                      <Typography.Text type="secondary">
                        {change.changedFields.join("、")}
                      </Typography.Text>
                    ) : null}
                  </Space>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="人员快照已经是最新状态" />
            )}
          </>
        ) : null}
      </Modal>

      <Modal
        title="玩家波次与排序偏好"
        open={preferencesOpen}
        width={760}
        onCancel={() => setPreferencesOpen(false)}
        onOk={() => void savePreferences()}
        okText="保存偏好"
      >
        <Typography.Paragraph type="secondary">
          可用波次留空表示全程可用；最大出场次数为空表示不额外限制。
        </Typography.Paragraph>
        <div className="preference-list">
          {preferenceDrafts.map((preference) => {
            const player = detail.participants.find(
              (participant) => participant.playerIdSnapshot === preference.playerId,
            );
            return (
              <Card size="small" key={preference.playerId}>
                <Typography.Text strong>
                  {player?.playerNameSnapshot ?? preference.playerId}
                </Typography.Text>
                <Row gutter={[12, 12]} className="preference-fields">
                  <Col xs={24} md={12}>
                    <Space className="preference-availability-heading">
                      <Typography.Text type="secondary">可用波次</Typography.Text>
                      <Space size={4}>
                        <Switch
                          size="small"
                          checked={preference.allowedWaves === null}
                          onChange={(allWaves) =>
                            updatePreference(preference.playerId, {
                              allowedWaves: allWaves ? null : [],
                            })
                          }
                        />
                        全程可用
                      </Space>
                    </Space>
                    <Select
                      mode="multiple"
                      allowClear
                      className="full-width"
                      disabled={preference.allowedWaves === null}
                      placeholder={
                        preference.allowedWaves === null ? "全部波次" : "当前无可用波次"
                      }
                      value={preference.allowedWaves ?? []}
                      options={Array.from({ length: detail.waveCount }, (_, index) => ({
                        label: `第 ${index + 1} 波`,
                        value: index + 1,
                      }))}
                      onChange={(allowedWaves) =>
                        updatePreference(preference.playerId, { allowedWaves })
                      }
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Typography.Text type="secondary">最大出场</Typography.Text>
                    <InputNumber
                      min={1}
                      max={detail.waveCount}
                      className="full-width"
                      placeholder="不限"
                      value={preference.maxWaveCount}
                      onChange={(value) =>
                        updatePreference(preference.playerId, {
                          maxWaveCount: value,
                        })
                      }
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Space orientation="vertical" size={4}>
                      <Space>
                        <Switch
                          size="small"
                          checked={preference.preferEarly}
                          onChange={(preferEarly) =>
                            updatePreference(preference.playerId, { preferEarly })
                          }
                        />
                        优先靠前
                      </Space>
                      <Space>
                        <Switch
                          size="small"
                          checked={preference.preferContiguous}
                          onChange={(preferContiguous) =>
                            updatePreference(preference.playerId, { preferContiguous })
                          }
                        />
                        尽量连续
                      </Space>
                    </Space>
                  </Col>
                </Row>
              </Card>
            );
          })}
        </div>
      </Modal>
    </section>
  );
}

function ParticipantLabel({
  participant,
  compact = false,
}: {
  participant: ScheduleParticipant;
  compact?: boolean;
}) {
  return (
    <Space size={4} wrap={!compact}>
      <Tag color={participant.roleTypeSnapshot === "DAMAGE" ? "volcano" : "blue"}>
        {participant.roleTypeSnapshot === "DAMAGE" ? "C" : "奶"}
      </Tag>
      <span>{participant.playerNameSnapshot} · {participant.characterNameSnapshot}</span>
      {participant.isTreasureSnapshot ? <Tag color="gold">秘宝</Tag> : null}
    </Space>
  );
}
