import {
  CheckCircleOutlined,
  CopyOutlined,
  CrownOutlined,
  DownloadOutlined,
  HistoryOutlined,
  LockOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RedoOutlined,
  ReloadOutlined,
  SendOutlined,
  SettingOutlined,
  UndoOutlined,
  UnlockOutlined,
} from "@ant-design/icons";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
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
  Segmented,
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
  type GenerationResponse,
  type GenerationRun,
  type ScheduleCommandResponse,
  type ScheduleCopyPreview,
  type ScheduleDetail,
  type ScheduleOperation,
  type ScheduleParticipant,
  type SchedulePublishResponse,
  type SchedulePreference,
  type ScheduleSlot,
  type ScheduleSummary,
  type ScheduleSyncPreview,
  type ScheduleTeam,
  type ScheduleVersionSummary,
  type ScheduleWave,
  type ShareLinkCreated,
  type ValidationIssue,
  type ValidationReport,
} from "../../api/client";
import { useScheduleEditorStore } from "./scheduleEditorStore";

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
  FALLBACK_COMPOSITION_FEASIBLE: "可使用备用组成补足完整队伍",
  FULL_COMPOSITION_INFEASIBLE: "当前角色类型无法组成全部完整队伍",
  UNUSABLE_ROLE_SURPLUS: "部分角色超出合法组成可容纳数量",
  STRENGTH_ORDER_CHECK_ON_GENERATION: "强度顺序将在生成时校验",
  MISSING_WAVE_CORE: "完整波次缺少核心角色",
  DAMAGE_ORDER_VIOLATION: "C 强度顺序未满足",
  BUFFER_ORDER_VIOLATION: "奶强度顺序未满足",
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
  const [copyTargetVersionId, setCopyTargetVersionId] = useState("");
  const [copyWaveCount, setCopyWaveCount] = useState(1);
  const [copyPreview, setCopyPreview] = useState<ScheduleCopyPreview | null>(null);
  const [copyPending, setCopyPending] = useState(false);
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationPending, setGenerationPending] = useState(false);
  const [generationPreserveLocks, setGenerationPreserveLocks] = useState(true);
  const [generationTimeLimit, setGenerationTimeLimit] = useState(10);
  const [generationSeed, setGenerationSeed] = useState(42);
  const [latestGeneration, setLatestGeneration] = useState<GenerationRun | null>(null);
  const [editorPending, setEditorPending] = useState(false);
  const [versions, setVersions] = useState<ScheduleVersionSummary[]>([]);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishPending, setPublishPending] = useState(false);
  const [confirmPublishWarnings, setConfirmPublishWarnings] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [waveCount, setWaveCount] = useState(1);
  const [createForm] = Form.useForm();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const {
    viewMode,
    selectedWaveNo,
    undoStack,
    redoStack,
    setViewMode,
    setSelectedWaveNo,
    record,
    commitUndo,
    commitRedo,
    reset: resetEditor,
  } = useScheduleEditorStore();

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

  const copyVersionOptions = useMemo(() => {
    if (!detail) return [];
    const sourceDungeon = dungeons.find((dungeon) =>
      dungeon.versions.some((version) => version.id === detail.dungeonVersionId),
    );
    return (sourceDungeon?.versions ?? [])
      .filter(
        (version) =>
          version.status === "PUBLISHED" || version.id === detail.dungeonVersionId,
      )
      .map((version) => ({
        label: `${sourceDungeon?.name ?? "副本"} · v${version.versionNo}${
          version.id === detail.dungeonVersionId ? "（当前）" : ""
        }`,
        value: version.id,
      }));
  }, [detail, dungeons]);

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
    setLatestGeneration(null);
  };

  const openSchedule = async (scheduleId: string) => {
    try {
      const [schedule, runs, versionResult] = await Promise.all([
        api<ScheduleDetail>(`/schedules/${scheduleId}`),
        api<{ items: GenerationRun[] }>(`/schedules/${scheduleId}/generation-runs`),
        api<{ items: ScheduleVersionSummary[] }>(`/schedules/${scheduleId}/versions`),
      ]);
      applyDetail(schedule);
      resetEditor();
      setLatestGeneration(runs.items[0] ?? null);
      setVersions(versionResult.items);
    } catch (error) {
      onError(error);
    }
  };

  const executeEditorOperations = async (
    operations: ScheduleOperation[],
    historyMode: "record" | "undo" | "redo" = "record",
  ) => {
    if (!detail || editorPending) return;
    setEditorPending(true);
    try {
      const response = await api<ScheduleCommandResponse>(`/schedules/${detail.id}/commands`, {
        method: "POST",
        body: JSON.stringify({
          operationId: globalThis.crypto.randomUUID(),
          baseRevision: detail.revision,
          operations,
        }),
      });
      applyDetail(response.schedule);
      if (historyMode === "record") {
        record({ forward: operations, inverse: response.inverseOperations });
      } else if (historyMode === "undo") {
        commitUndo();
      } else {
        commitRedo(response.inverseOperations);
      }
      onSuccess(
        historyMode === "record" ? "排表已更新" : historyMode === "undo" ? "已撤销" : "已恢复",
      );
    } catch (error) {
      onError(error);
    } finally {
      setEditorPending(false);
    }
  };

  const undo = async () => {
    const entry = undoStack.at(-1);
    if (entry) await executeEditorOperations(entry.inverse, "undo");
  };

  const redo = async () => {
    const entry = redoStack.at(-1);
    if (entry) await executeEditorOperations(entry.forward, "redo");
  };

  const onDragEnd = async ({ active, over }: DragEndEvent) => {
    if (!detail || !over) return;
    const participantId = String(active.id).replace(/^participant:/, "");
    const slotId = String(over.id).replace(/^slot:/, "");
    const target = detail.waves
      .flatMap((wave) => wave.teams)
      .flatMap((team) => team.slots)
      .find((slot) => slot.id === slotId);
    if (!target || target.participantId === participantId) return;
    await executeEditorOperations([
      target.participantId
        ? {
            type: "SWAP_PARTICIPANTS",
            participantId,
            otherParticipantId: target.participantId,
          }
        : { type: "MOVE_PARTICIPANT", participantId, toSlotId: target.id },
    ]);
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
      resetEditor();
      setVersions([]);
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

  const previewCopy = async () => {
    if (!detail || !copyTargetVersionId) return;
    setCopyPending(true);
    try {
      setCopyPreview(
        await api<ScheduleCopyPreview>(`/schedules/${detail.id}/copy/preview`, {
          method: "POST",
          body: JSON.stringify({
            baseRevision: detail.revision,
            targetDungeonVersionId: copyTargetVersionId,
            waveCount: copyWaveCount,
          }),
        }),
      );
    } catch (error) {
      onError(error);
    } finally {
      setCopyPending(false);
    }
  };

  const copySchedule = async () => {
    if (!detail || !copyPreview) return;
    setCopyPending(true);
    try {
      const copied = await api<ScheduleDetail>(`/schedules/${detail.id}/copy`, {
        method: "POST",
        body: JSON.stringify({
          baseRevision: detail.revision,
          name: copyName,
          targetDungeonVersionId: copyTargetVersionId,
          waveCount: copyWaveCount,
          migrationFingerprint: copyPreview.migrationFingerprint,
        }),
      });
      setCopyOpen(false);
      setCopyPreview(null);
      await loadList();
      applyDetail(copied);
      onSuccess("排表已复制，角色次数和队伍位置已重置");
    } catch (error) {
      onError(error);
    } finally {
      setCopyPending(false);
    }
  };

  const validate = async () => {
    if (!detail) return;
    try {
      setValidation(
        await api<ValidationReport>(`/schedules/${detail.id}/validate`, {
          method: "POST",
          body: JSON.stringify({ baseRevision: detail.revision }),
        }),
      );
      await loadList();
    } catch (error) {
      onError(error);
    }
  };

  const generate = async () => {
    if (!detail) return;
    setGenerationPending(true);
    try {
      const response = await api<GenerationResponse>(`/schedules/${detail.id}/generate`, {
        method: "POST",
        body: JSON.stringify({
          baseRevision: detail.revision,
          preserveLocks: generationPreserveLocks,
          randomSeed: generationSeed,
          timeLimitSeconds: generationTimeLimit,
        }),
      });
      applyDetail(response.schedule);
      setLatestGeneration(response.run);
      setGenerationOpen(false);
      await loadList();
      onSuccess(
        response.run.status === "PARTIAL"
          ? "已生成部分排表，请查看未分配原因"
          : "自动排表已生成",
      );
    } catch (error) {
      onError(error);
    } finally {
      setGenerationPending(false);
    }
  };

  const publish = async () => {
    if (!detail) return;
    setPublishPending(true);
    try {
      const response = await api<SchedulePublishResponse>(`/schedules/${detail.id}/publish`, {
        method: "POST",
        body: JSON.stringify({
          baseRevision: detail.revision,
          confirmWarnings: confirmPublishWarnings,
        }),
      });
      applyDetail(response.schedule);
      setVersions((current) => [response.version, ...current]);
      setPublishOpen(false);
      setConfirmPublishWarnings(false);
      resetEditor();
      await loadList();
      onSuccess(`排表已发布为 v${response.version.versionNo}`);
    } catch (error) {
      onError(error);
    } finally {
      setPublishPending(false);
    }
  };

  const restoreVersion = async (versionNo: number) => {
    if (!detail) return;
    try {
      const restored = await api<ScheduleDetail>(
        `/schedules/${detail.id}/versions/${versionNo}/restore-as-draft`,
        {
          method: "POST",
          body: JSON.stringify({ baseRevision: detail.revision }),
        },
      );
      applyDetail(restored);
      resetEditor();
      setHistoryOpen(false);
      await loadList();
      onSuccess(`已从发布版本 v${versionNo} 恢复为草稿`);
    } catch (error) {
      onError(error);
    }
  };

  const confirmRestoreVersion = (versionNo: number) => {
    Modal.confirm({
      title: `恢复发布版本 v${versionNo}？`,
      content: "当前草稿布局会被该发布版本替换；发布历史不会被删除。",
      okText: "确认恢复",
      cancelText: "取消",
      onOk: () => restoreVersion(versionNo),
    });
  };

  const createShare = async (version: ScheduleVersionSummary) => {
    try {
      const link = await api<ShareLinkCreated>(`/schedule-versions/${version.id}/share-links`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setShareUrl(`${window.location.origin}/share/${link.token}`);
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
  const selectedIdSet = new Set(selectedIds);
  const selectedParticipants = detail.participants.filter((participant) =>
    selectedIdSet.has(participant.id),
  );
  const participantSelectionDirty = detail.participants.some(
    (participant) => participant.isSelected !== selectedIdSet.has(participant.id),
  );
  const waveCountDirty = waveCount !== detail.waveCount;
  const hasUnsavedChanges = participantSelectionDirty || waveCountDirty;
  const damageCount = selectedParticipants.filter(
    (participant) => participant.roleTypeSnapshot === "DAMAGE",
  ).length;
  const assignedParticipantIds = new Set(
    detail.waves
      .flatMap((wave) => wave.teams)
      .flatMap((team) => team.slots)
      .flatMap((slot) => (slot.participantId ? [slot.participantId] : [])),
  );
  const unassignedParticipants = selectedParticipants.filter(
    (participant) => !assignedParticipantIds.has(participant.id),
  );
  const visibleWaves =
    viewMode === "overview"
      ? detail.waves
      : detail.waves.filter((wave) => wave.waveNo === selectedWaveNo);

  return (
    <section>
      <div className="section-heading">
        <div>
          <Button
            type="link"
            className="schedule-back"
            onClick={() => {
              setDetail(null);
              setLatestGeneration(null);
              setVersions([]);
              setShareUrl("");
              resetEditor();
            }}
          >
            ← 返回排表列表
          </Button>
          <Typography.Title level={2}>{detail.name}</Typography.Title>
          <Typography.Text type="secondary">
            {detail.waveCount} 波 · revision {detail.revision} · {detail.status}
          </Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
            发布历史 {versions.length ? `(${versions.length})` : ""}
          </Button>
          <Button
            type="primary"
            icon={<SendOutlined />}
            disabled={
              hasUnsavedChanges || detail.status === "ARCHIVED" || detail.status === "PUBLISHED"
            }
            onClick={() => setPublishOpen(true)}
          >
            发布排表
          </Button>
          <Button
            icon={<CopyOutlined />}
            disabled={hasUnsavedChanges}
            onClick={() => {
              setCopyName(`${detail.name} - 副本`);
              setCopyTargetVersionId(detail.dungeonVersionId);
              setCopyWaveCount(detail.waveCount);
              setCopyPreview(null);
              setCopyOpen(true);
            }}
          >
            复制排表
          </Button>
          <Button icon={<SettingOutlined />} disabled={hasUnsavedChanges} onClick={openPreferences}>
            玩家偏好
          </Button>
          <Button
            icon={<ReloadOutlined />}
            disabled={hasUnsavedChanges}
            onClick={() => void previewSync()}
          >
            同步角色
          </Button>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            disabled={hasUnsavedChanges}
            onClick={() => void validate()}
          >
            运行预检查
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            disabled={hasUnsavedChanges || detail.status === "ARCHIVED"}
            onClick={() => setGenerationOpen(true)}
          >
            {detail.waves.some((wave) =>
              wave.teams.some((team) => team.slots.some((slot) => slot.participantId)),
            )
              ? "重新生成"
              : "自动排表"}
          </Button>
        </Space>
      </div>

      {hasUnsavedChanges ? (
        <Alert
          className="schedule-panel"
          type="warning"
          showIcon
          title="当前有尚未保存的排表设置"
          description="请先保存参团角色选择或更新波数，再进行复制、角色同步和预检查。"
        />
      ) : null}

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
                  description={describeIssue(issue)}
                  showIcon
                />
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有问题" />
          )}
        </Card>
      ) : null}

      {latestGeneration ? (
        <GenerationSummary run={latestGeneration} participants={detail.participants} />
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

      <Card className="schedule-panel editor-toolbar">
        <Space wrap>
          <Segmented
            value={viewMode}
            onChange={(value) => setViewMode(value as "overview" | "wave")}
            options={[
              { label: "总览", value: "overview" },
              { label: "单波", value: "wave" },
            ]}
          />
          {viewMode === "wave" ? (
            <Select
              value={selectedWaveNo}
              onChange={setSelectedWaveNo}
              options={detail.waves.map((wave) => ({
                label: `第 ${wave.waveNo} 波`,
                value: wave.waveNo,
              }))}
              style={{ width: 128 }}
            />
          ) : null}
          <Button
            icon={<UndoOutlined />}
            disabled={!undoStack.length || editorPending}
            onClick={() => void undo()}
          >
            撤销
          </Button>
          <Button
            icon={<RedoOutlined />}
            disabled={!redoStack.length || editorPending}
            onClick={() => void redo()}
          >
            恢复
          </Button>
          <Typography.Text type="secondary">拖动角色到空位，拖到其他角色上可直接交换</Typography.Text>
        </Space>
      </Card>

      <DndContext sensors={sensors} onDragEnd={(event) => void onDragEnd(event)}>
        <Card title={`未分配角色 · ${unassignedParticipants.length}`} className="schedule-panel">
          <div className="unassigned-pool">
            {unassignedParticipants.length ? (
              unassignedParticipants.map((participant) => (
                <DraggableParticipant
                  key={participant.id}
                  participant={participant}
                  disabled={participant.isLocked || editorPending}
                />
              ))
            ) : (
              <Typography.Text type="secondary">所有参团角色都已安排</Typography.Text>
            )}
          </div>
        </Card>
        <div className="wave-list">
          {visibleWaves.map((wave) => (
            <EditorWave
              key={wave.id}
              wave={wave}
              participantsById={participantsById}
              disabled={editorPending}
              onOperation={(operation) => void executeEditorOperations([operation])}
            />
          ))}
        </div>
      </DndContext>

      <Modal
        title="发布排表"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={() => void publish()}
        okText="确认发布"
        confirmLoading={publishPending}
      >
        <Alert
          type="info"
          showIcon
          title="发布后会保存不可变快照"
          description="以后继续编辑会自动回到草稿状态，已发布版本及其导出内容不会改变。"
        />
        <Checkbox
          className="publish-warning-confirm"
          checked={confirmPublishWarnings}
          onChange={(event) => setConfirmPublishWarnings(event.target.checked)}
        >
          我确认在存在非阻断警告时仍然发布
        </Checkbox>
      </Modal>

      <Modal
        title="发布历史"
        open={historyOpen}
        onCancel={() => setHistoryOpen(false)}
        footer={null}
        width={760}
      >
        {versions.length ? (
          <div className="version-history-list">
            {versions.map((version) => (
              <Card
                size="small"
                key={version.id}
                title={`v${version.versionNo}`}
                extra={new Date(version.publishedAt).toLocaleString()}
              >
                <Space wrap>
                  <Button
                    size="small"
                    icon={<HistoryOutlined />}
                    onClick={() => confirmRestoreVersion(version.versionNo)}
                  >
                    恢复为草稿
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    href={`/api/v1/schedule-versions/${version.id}/exports/image`}
                  >
                    长图
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    href={`/api/v1/schedule-versions/${version.id}/exports/excel`}
                  >
                    Excel
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    href={`/api/v1/schedule-versions/${version.id}/exports/text`}
                  >
                    文本
                  </Button>
                  <Button
                    size="small"
                    icon={<SendOutlined />}
                    onClick={() => void createShare(version)}
                  >
                    创建只读链接
                  </Button>
                </Space>
                <Typography.Text type="secondary" className="version-hash">
                  revision {version.sourceRevision} · {version.snapshotHash.slice(0, 12)}
                </Typography.Text>
              </Card>
            ))}
          </div>
        ) : (
          <Empty description="尚未发布任何版本" />
        )}
      </Modal>

      <Modal
        title="只读分享链接"
        open={Boolean(shareUrl)}
        onCancel={() => setShareUrl("")}
        footer={<Button onClick={() => setShareUrl("")}>关闭</Button>}
      >
        <Typography.Paragraph type="secondary">
          链接只展示对应的不可变发布版本，不会随草稿修改而变化。
        </Typography.Paragraph>
        <Input value={shareUrl} readOnly />
      </Modal>

      <Modal
        title="自动排表"
        open={generationOpen}
        onCancel={() => setGenerationOpen(false)}
        onOk={() => void generate()}
        okText="开始生成"
        confirmLoading={generationPending}
      >
        <Typography.Paragraph type="secondary">
          求解器会优先安排更多角色、填满前面波次并优化队伍组成、核心秘宝、跨波平衡和强度顺序。
        </Typography.Paragraph>
        <Space orientation="vertical" className="full-width" size="middle">
          <Space>
            <Switch
              checked={generationPreserveLocks}
              onChange={setGenerationPreserveLocks}
            />
            保留当前锁定安排
          </Space>
          <Row gutter={12} className="full-width">
            <Col span={12}>
              <Typography.Text type="secondary">求解时限（秒）</Typography.Text>
              <InputNumber
                min={1}
                max={60}
                className="full-width"
                value={generationTimeLimit}
                onChange={(value) => setGenerationTimeLimit(value ?? 10)}
              />
            </Col>
            <Col span={12}>
              <Typography.Text type="secondary">随机种子</Typography.Text>
              <InputNumber
                min={0}
                max={2_147_483_647}
                className="full-width"
                value={generationSeed}
                onChange={(value) => setGenerationSeed(value ?? 42)}
              />
            </Col>
          </Row>
        </Space>
      </Modal>

      <Modal
        title="复制排表"
        open={copyOpen}
        onCancel={() => {
          setCopyOpen(false);
          setCopyPreview(null);
        }}
        onOk={() => void (copyPreview ? copySchedule() : previewCopy())}
        okText={copyPreview ? "确认创建" : "预览迁移"}
        confirmLoading={copyPending}
        okButtonProps={{ disabled: !copyName.trim() || !copyTargetVersionId }}
      >
        <Typography.Paragraph type="secondary">
          将复制副本版本、波数、参团选择和玩家偏好；角色使用最新档案数据，队伍位置与锁定状态会清空。
        </Typography.Paragraph>
        <Input
          value={copyName}
          maxLength={160}
          onChange={(event) => {
            setCopyName(event.target.value);
            setCopyPreview(null);
          }}
          placeholder="新排表名称"
        />
        <Row gutter={12} className="copy-fields">
          <Col span={16}>
            <Typography.Text type="secondary">目标副本版本</Typography.Text>
            <Select
              className="full-width"
              value={copyTargetVersionId}
              options={copyVersionOptions}
              onChange={(value) => {
                setCopyTargetVersionId(value);
                setCopyPreview(null);
              }}
            />
          </Col>
          <Col span={8}>
            <Typography.Text type="secondary">波数</Typography.Text>
            <InputNumber
              min={1}
              max={50}
              className="full-width"
              value={copyWaveCount}
              onChange={(value) => {
                setCopyWaveCount(value ?? 1);
                setCopyPreview(null);
              }}
            />
          </Col>
        </Row>
        {copyPreview ? (
          <div className="copy-preview">
            <Alert
              type={copyPreview.changes.length ? "warning" : "success"}
              showIcon
              title={
                copyPreview.changes.length
                  ? `确认以下 ${copyPreview.changes.length} 项变化`
                  : "副本结构与当前排表一致"
              }
            />
            {copyPreview.changes.map((change) => (
              <div className="copy-change" key={change.code}>
                <Tag>{change.code}</Tag>
                <Typography.Text>{change.description}</Typography.Text>
              </div>
            ))}
          </div>
        ) : null}
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

function EditorWave({
  wave,
  participantsById,
  disabled,
  onOperation,
}: {
  wave: ScheduleWave;
  participantsById: Map<string, ScheduleParticipant>;
  disabled: boolean;
  onOperation: (operation: ScheduleOperation) => void;
}) {
  return (
    <Card
      title={`第 ${wave.waveNo} 波`}
      extra={
        <Space>
          <Typography.Text type="secondary">
            C {wave.damageTotal} 亿 · 奶 {wave.bufferTotal}
          </Typography.Text>
          <Button
            size="small"
            icon={wave.isLocked ? <UnlockOutlined /> : <LockOutlined />}
            disabled={disabled}
            onClick={() =>
              onOperation({ type: "LOCK_WAVE", waveId: wave.id, locked: !wave.isLocked })
            }
          >
            {wave.isLocked ? "解锁波次" : "锁定波次"}
          </Button>
        </Space>
      }
      className="schedule-panel wave-card"
    >
      <Row gutter={[12, 12]}>
        {wave.teams.map((team) => (
          <Col xs={24} xl={Math.max(6, Math.floor(24 / wave.teams.length))} key={team.id}>
            <Card
              size="small"
              title={`${team.displayNameSnapshot} · ${team.compositionCode}`}
              extra={`C ${team.damageTotal} · 奶 ${team.bufferTotal}`}
              className="team-card"
              style={{ borderTopColor: team.displayColorSnapshot }}
            >
              <div className="team-slots">
                {team.slots.map((slot) => (
                  <EditorSlot
                    key={slot.id}
                    slot={slot}
                    team={team}
                    wave={wave}
                    participant={
                      slot.participantId ? participantsById.get(slot.participantId) : undefined
                    }
                    disabled={disabled}
                    onOperation={onOperation}
                  />
                ))}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </Card>
  );
}

function EditorSlot({
  slot,
  team,
  wave,
  participant,
  disabled,
  onOperation,
}: {
  slot: ScheduleSlot;
  team: ScheduleTeam;
  wave: ScheduleWave;
  participant?: ScheduleParticipant;
  disabled: boolean;
  onOperation: (operation: ScheduleOperation) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `slot:${slot.id}`,
    disabled: disabled || slot.isLocked || wave.isLocked,
  });
  const core = participant
    ? wave.specialAssignments.find((assignment) => assignment.participantId === participant.id)
    : undefined;
  const moveDisabled = disabled || slot.isLocked || wave.isLocked || Boolean(participant?.isLocked);
  return (
    <div
      ref={setNodeRef}
      className={`team-slot editor-slot${isOver ? " editor-slot-over" : ""}${
        slot.isLocked ? " editor-slot-locked" : ""
      }`}
    >
      <div className="editor-slot-content">
        {participant ? (
          <DraggableParticipant participant={participant} core={Boolean(core)} disabled={moveDisabled} />
        ) : (
          <Typography.Text type="secondary">位置 {slot.slotNo} · 待排</Typography.Text>
        )}
      </div>
      <Space size={2} className="editor-slot-actions" onPointerDown={(event) => event.stopPropagation()}>
        {participant?.isTreasureSnapshot ? (
          <Button
            type="text"
            size="small"
            title={core ? "取消本波核心" : "设为本波核心"}
            icon={<CrownOutlined />}
            disabled={disabled || wave.isLocked}
            onClick={() =>
              onOperation(
                core
                  ? {
                      type: "CLEAR_WAVE_CORE",
                      waveId: wave.id,
                      ruleCode: core.ruleCode,
                    }
                  : {
                      type: "SET_WAVE_CORE",
                      waveId: wave.id,
                      participantId: participant.id,
                    },
              )
            }
          />
        ) : null}
        {participant ? (
          <>
            <Button
              type="text"
              size="small"
              title={participant.isLocked ? "解锁角色" : "锁定角色"}
              icon={participant.isLocked ? <UnlockOutlined /> : <LockOutlined />}
              disabled={disabled}
              onClick={() =>
                onOperation({
                  type: "LOCK_PARTICIPANT",
                  participantId: participant.id,
                  locked: !participant.isLocked,
                })
              }
            />
            <Button
              type="text"
              size="small"
              danger
              disabled={moveDisabled}
              onClick={() =>
                onOperation({ type: "UNASSIGN_PARTICIPANT", participantId: participant.id })
              }
            >
              移出
            </Button>
          </>
        ) : null}
        <Button
          type="text"
          size="small"
          title={slot.isLocked ? "解锁位置" : "锁定位置"}
          icon={slot.isLocked ? <UnlockOutlined /> : <LockOutlined />}
          disabled={disabled || wave.isLocked}
          onClick={() =>
            onOperation({ type: "LOCK_SLOT", slotId: slot.id, locked: !slot.isLocked })
          }
        />
      </Space>
    </div>
  );
}

function DraggableParticipant({
  participant,
  core = false,
  disabled,
}: {
  participant: ScheduleParticipant;
  core?: boolean;
  disabled: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `participant:${participant.id}`,
    disabled,
  });
  return (
    <div
      ref={setNodeRef}
      className={`draggable-participant${isDragging ? " dragging" : ""}`}
      style={{ transform: CSS.Translate.toString(transform) }}
      {...listeners}
      {...attributes}
    >
      <ParticipantLabel participant={participant} compact core={core} />
    </div>
  );
}

function ParticipantLabel({
  participant,
  compact = false,
  core = false,
}: {
  participant: ScheduleParticipant;
  compact?: boolean;
  core?: boolean;
}) {
  return (
    <Space size={4} wrap={!compact}>
      <Tag color={participant.roleTypeSnapshot === "DAMAGE" ? "volcano" : "blue"}>
        {participant.roleTypeSnapshot === "DAMAGE" ? "C" : "奶"}
      </Tag>
      <span>{participant.playerNameSnapshot} · {participant.characterNameSnapshot}</span>
      {participant.isTreasureSnapshot ? <Tag color="gold">秘宝</Tag> : null}
      {core ? <Tag color="gold">本波核心</Tag> : null}
      {participant.unassignedReason ? (
        <Tag color="warning">
          {describeUnassignedReason(participant.unassignedReason)}
        </Tag>
      ) : null}
    </Space>
  );
}

function GenerationSummary({
  run,
  participants,
}: {
  run: GenerationRun;
  participants: ScheduleParticipant[];
}) {
  const summary = run.objectiveSummary;
  const participantById = new Map(participants.map((participant) => [participant.id, participant]));
  const unassigned = run.diagnostics?.unassigned ?? [];
  const issues = run.diagnostics?.issues ?? [];
  return (
    <Card title="最近一次自动排表" className="schedule-panel">
      <Space wrap className="generation-summary-tags">
        <Tag color={run.status === "SUCCEEDED" ? "green" : "orange"}>{run.status}</Tag>
        <Tag>耗时 {run.durationMs ?? 0} ms</Tag>
        <Tag>种子 {run.randomSeed}</Tag>
        {summary ? (
          <>
            <Tag color="blue">
              已安排 {summary.assignedCount}/{summary.participantCount}
            </Tag>
            <Tag color="cyan">完整波次 {summary.completeWaveCount}</Tag>
            <Tag color="purple">完整队伍 {summary.completeTeamCount}</Tag>
            <Tag color="gold">核心满足 {summary.specialRuleSatisfiedCount}</Tag>
            <Tag color={summary.strengthOrderViolationCount ? "orange" : "green"}>
              强度顺序冲突 {summary.strengthOrderViolationCount}
            </Tag>
          </>
        ) : null}
      </Space>
      {unassigned.length ? (
        <div className="generation-diagnostics">
          <Typography.Text strong>未分配角色</Typography.Text>
          {unassigned.map((item) => {
            const participant = participantById.get(item.participantId);
            return (
              <Alert
                key={item.participantId}
                type="warning"
                showIcon
                title={
                  participant
                    ? `${participant.playerNameSnapshot} · ${participant.characterNameSnapshot}`
                    : item.participantId
                }
                description={describeGenerationDiagnostic(item.code, item.messageParams)}
              />
            );
          })}
        </div>
      ) : null}
      {issues.length ? (
        <div className="generation-diagnostics">
          <Typography.Text strong>优化冲突</Typography.Text>
          {issues.map((issue, index) => (
            <Alert
              key={`${issue.code}-${index}`}
              type={issue.severity === "ERROR" ? "error" : "warning"}
              showIcon
              title={ISSUE_LABELS[issue.code] ?? issue.code}
              description={describeGenerationDiagnostic(issue.code, issue.messageParams)}
            />
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function describeUnassignedReason(reason: Record<string, unknown>): string {
  if (reason.message === "角色或玩家已停用" || reason.code === "SOURCE_INACTIVE") {
    return "档案已停用，待处理";
  }
  const labels: Record<string, string> = {
    UNASSIGNED_NO_AVAILABLE_WAVE: "无可用波次",
    UNASSIGNED_PLAYER_CONFLICT: "玩家波次冲突",
    UNASSIGNED_ROLE_COMPOSITION: "角色类型无法组成合法队伍",
    UNASSIGNED_CAPACITY: "排表容量不足",
  };
  return labels[String(reason.code)] ?? "待处理";
}

function describeGenerationDiagnostic(
  code: string,
  params: Record<string, unknown>,
): string {
  switch (code) {
    case "UNASSIGNED_NO_AVAILABLE_WAVE":
      return "该玩家没有允许参加的波次。";
    case "UNASSIGNED_PLAYER_CONFLICT":
      return params.maxWaveCount
        ? `该玩家已达到最多 ${params.maxWaveCount} 波的限制。`
        : "该玩家在所有可用波次都已有其他角色。";
    case "UNASSIGNED_CAPACITY":
      return `排表容量 ${params.capacity} 已用完。`;
    case "UNASSIGNED_ROLE_COMPOSITION":
      return `剩余 ${params.roleType === "DAMAGE" ? "C" : "奶"} 无法组成合法完整队伍。`;
    case "MISSING_WAVE_CORE":
      return `第 ${params.waveNo} 波缺少规则 ${params.ruleCode} 要求的核心角色。`;
    case "DAMAGE_ORDER_VIOLATION":
    case "BUFFER_ORDER_VIOLATION":
      return `第 ${params.waveNo} 波 ${params.strongerTeamKey} 弱于 ${params.weakerTeamKey}。`;
    default:
      return Object.entries(params)
        .map(([key, value]) => `${key}: ${String(value)}`)
        .join("；");
  }
}

function describeIssue(issue: ValidationIssue): string {
  const params = issue.message_params;
  switch (issue.code) {
    case "CAPACITY_EXCEEDED":
      return `容量 ${params.capacity}，当前 ${params.current}，请减少角色或增加波数。`;
    case "PARTICIPANT_SHORTAGE":
      return `容量 ${params.capacity}，当前 ${params.current}，还缺 ${params.shortage} 个角色。`;
    case "DAMAGE_IDEAL_SHORTAGE":
    case "BUFFER_BASE_SHORTAGE":
    case "TREASURE_SHORTAGE":
      return `需要 ${params.required}，当前 ${params.current}，缺少 ${params.shortage}。`;
    case "PLAYER_WAVE_CAPACITY_INSUFFICIENT":
      return `${params.playerName} 选择了 ${params.selected} 个角色，但最多只能安排 ${params.available} 波。`;
    case "FALLBACK_COMPOSITION_FEASIBLE":
      return `可用 ${params.damageUsed} 个 C 和 ${params.buffersUsed} 个奶组成全部完整队伍。`;
    case "FULL_COMPOSITION_INFEASIBLE":
      return `当前有 ${params.damage} 个 C、${params.buffers} 个奶；最接近的完整组成需要 ${params.requiredDamage} 个 C 和 ${params.requiredBuffers} 个奶，仍缺 ${params.damageShortage} 个 C、${params.bufferShortage} 个奶。`;
    case "UNUSABLE_ROLE_SURPLUS":
      return `${params.roleType === "DAMAGE" ? "C" : "奶"} 超出合法完整组成上限 ${params.surplus} 个。`;
    case "STRENGTH_ORDER_CHECK_ON_GENERATION":
      return String(params.reason);
    default:
      return Object.entries(params)
        .map(([key, value]) => `${key}: ${String(value)}`)
        .join("；");
  }
}
