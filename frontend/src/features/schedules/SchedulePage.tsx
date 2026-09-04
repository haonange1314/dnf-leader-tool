import {
  CheckCircleOutlined,
  CopyOutlined,
  DownOutlined,
  DownloadOutlined,
  EyeOutlined,
  HistoryOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RedoOutlined,
  ReloadOutlined,
  SendOutlined,
  SettingOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Dropdown,
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
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type EditLock,
  type Dungeon,
  type GenerationResponse,
  type GenerationRun,
  type ScheduleCommandResponse,
  type ScheduleCopyPreview,
  type ScheduleDetail,
  type ScheduleOperation,
  type SchedulePublicationCheck,
  type RuleResolutionIssue,
  type ScheduleRuleSet,
  type ScheduleRuleSetList,
  type ScheduleRuleSetMutationResponse,
  type ScheduleParticipant,
  type SchedulePublishResponse,
  type SchedulePreference,
  type ScheduleSlot,
  type ScheduleSummary,
  type ScheduleSyncPreview,
  type ScheduleVersionSummary,
  type ScheduleVersionView,
  type ShareLinkView,
  type ShareLinkCreated,
  type ValidationIssue,
  type ValidationReport,
  type User,
  setScheduleEditLockToken,
} from "../../api/client";
import { useScheduleEditorStore } from "./scheduleEditorStore";
import {
  ScheduleDraggableParticipant,
  ScheduleEditorWave,
  ScheduleParticipantLabel,
  ScheduleUnassignedDropZone,
} from "./ScheduleEditor";

interface Props {
  userRole: User["role"];
  permissions?: string[];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

const ISSUE_LABELS: Record<string, string> = {
  CAPACITY_EXCEEDED: "参团角色超过排表容量",
  PARTICIPANT_SHORTAGE: "参团角色少于排表容量",
  DISTINCT_PLAYER_SHORTAGE: "每波可用玩家人数不足",
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
  TEAM_INCOMPLETE: "队伍存在待补位置",
  TEAM_COMPOSITION_INVALID: "队伍组成不符合副本规则",
  PLAYER_DUPLICATE_IN_WAVE: "同一玩家在同一波使用多个角色",
  PARTICIPANT_WAVE_NOT_ALLOWED: "角色被安排到玩家不可用波次",
  PLAYER_MAX_WAVE_COUNT_EXCEEDED: "玩家出场次数超过上限",
  UNASSIGNED_SELECTED_PARTICIPANTS: "仍有已选角色未分配",
};

const OBJECTIVE_STAGE_LABELS: Record<string, string> = {
  ASSIGNED_COUNT: "安排人数",
  WAVE_FILL_SPREAD: "波次填充",
  COMPLETENESS: "完整波次与队伍",
  EARLY_FILL: "空位靠后",
  COMPOSITION_PRIORITY: "优先组成",
  SPECIAL_ROLE: "特殊核心",
  STRENGTH_ORDER: "队伍强度顺序",
  BALANCE_DAMAGE: "C 跨波平衡",
  BALANCE_BUFFER: "奶跨波平衡",
  SPECIAL_COMPANION: "核心搭配",
  PLAYER_PREFERENCE: "玩家偏好",
  SCHEDULE_RULES: "本次排表要求",
};

const RULE_TYPE_LABELS: Record<string, string> = {
  PLAYER_ALLOWED_WAVES: "玩家仅可用波次",
  PLAYER_FORBIDDEN_WAVES: "玩家禁用波次",
  PLAYERS_NOT_SAME_WAVE: "玩家不同波",
  CHARACTER_REQUIRED_WAVE: "角色固定波次",
  CHARACTER_REQUIRED_TEAM: "角色固定队伍",
  PLAYER_PREFER_WAVE_RANGE: "玩家偏好波次",
  PLAYER_PREFER_CONTIGUOUS: "玩家连续上号",
  CHARACTER_PREFER_TEAM: "角色偏好队伍",
};

const RULE_ISSUE_LABELS: Record<string, string> = {
  RULE_SET_TYPE_UNSUPPORTED: "暂不支持的要求",
  RULE_SET_CANDIDATE_DUPLICATED: "解析结果包含重复规则",
  RULE_SET_REFERENCE_NOT_FOUND: "未找到对应人员或角色",
  RULE_SET_REFERENCE_AMBIGUOUS: "名称对应多个候选",
  RULE_SET_WAVE_OUT_OF_RANGE: "波次超出当前排表范围",
  RULE_SET_HARD_CONFLICT: "硬规则互相冲突",
};

const RULE_EVALUATION_LABELS: Record<
  NonNullable<GenerationRun["ruleEvaluation"]>[number]["status"],
  { label: string; color?: string }
> = {
  SATISFIED: { label: "已满足", color: "green" },
  UNSATISFIED: { label: "未满足", color: "orange" },
  BLOCKED: { label: "被阻断", color: "red" },
  NOT_APPLICABLE: { label: "未执行" },
};

const OBJECTIVE_OUTCOME_LABELS = {
  OPTIMAL: "已证明最优",
  TARGET_REACHED: "达到理论界",
  FEASIBLE: "限时可行",
} as const;

const SCHEDULE_STATUS_LABELS: Record<ScheduleSummary["status"], string> = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
  ARCHIVED: "已归档",
};

const GENERATION_STATUS_LABELS: Record<GenerationRun["status"], string> = {
  RUNNING: "生成中",
  SUCCEEDED: "生成成功",
  PARTIAL: "部分完成",
  FAILED: "生成失败",
  STALE: "结果已失效",
};

function describeDungeonVersion(
  identity: { dungeonName: string; versionNo: number } | undefined,
  dungeonVersionId: string,
): string {
  return identity
    ? `${identity.dungeonName} · 副本第 ${identity.versionNo} 版`
    : `副本版本暂不可用（${dungeonVersionId.slice(0, 8)}）`;
}

export function SchedulePage({ userRole, permissions, onError, onSuccess }: Props) {
  const hasPermission = (code: string) =>
    permissions
      ? permissions.includes(code)
      : code.endsWith("_READ") || code === "SCHEDULE_EXPORT" || userRole !== "VIEWER";
  const canWrite = hasPermission("SCHEDULE_WRITE");
  const [schedules, setSchedules] = useState<ScheduleSummary[]>([]);
  const [showArchived, setShowArchived] = useState(false);
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
  const [generationFailure, setGenerationFailure] = useState<ApiError | null>(null);
  const [generationRuns, setGenerationRuns] = useState<GenerationRun[]>([]);
  const [generationHistoryOpen, setGenerationHistoryOpen] = useState(false);
  const [ruleSets, setRuleSets] = useState<ScheduleRuleSet[]>([]);
  const [ruleSourceText, setRuleSourceText] = useState("");
  const [ruleMaxSourceChars, setRuleMaxSourceChars] = useState(2000);
  const [ruleParsingEnabled, setRuleParsingEnabled] = useState(false);
  const [rulePending, setRulePending] = useState(false);
  const [rulePanelOpen, setRulePanelOpen] = useState(false);
  const [editorPending, setEditorPending] = useState(false);
  const [versions, setVersions] = useState<ScheduleVersionSummary[]>([]);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishPending, setPublishPending] = useState(false);
  const [confirmPublishWarnings, setConfirmPublishWarnings] = useState(false);
  const [publicationCheck, setPublicationCheck] = useState<SchedulePublicationCheck | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [versionPreview, setVersionPreview] = useState<ScheduleVersionView | null>(null);
  const [copyVersionTarget, setCopyVersionTarget] = useState<ScheduleVersionSummary | null>(null);
  const [copyVersionName, setCopyVersionName] = useState("");
  const [versionActionPending, setVersionActionPending] = useState(false);
  const [lifecyclePending, setLifecyclePending] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [shareVersion, setShareVersion] = useState<ScheduleVersionSummary | null>(null);
  const [shareLinks, setShareLinks] = useState<ShareLinkView[]>([]);
  const [shareExpiryDays, setShareExpiryDays] = useState<number | null>(7);
  const [sharePending, setSharePending] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [waveCount, setWaveCount] = useState(1);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [metadataName, setMetadataName] = useState("");
  const [metadataNote, setMetadataNote] = useState("");
  const [participantPanelOpen, setParticipantPanelOpen] = useState(false);
  const [unassignedPanelOpen, setUnassignedPanelOpen] = useState(false);
  const [unassignedRoleFilter, setUnassignedRoleFilter] = useState<"ALL" | "DAMAGE" | "BUFFER">("ALL");
  const [unassignedSort, setUnassignedSort] = useState<"ORDER" | "SCORE_DESC" | "PLAYER">("ORDER");
  const [preferencesSelectedOnly, setPreferencesSelectedOnly] = useState(true);
  const [editLock, setEditLock] = useState<EditLock | null>(null);
  const [editLockPending, setEditLockPending] = useState(false);
  const editLockRef = useRef<{ scheduleId: string; token: string } | null>(null);
  const [createForm] = Form.useForm();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
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
            label: `${dungeon.name} · 第 ${version.versionNo} 版`,
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
        label: `${sourceDungeon?.name ?? "副本"} · 第 ${version.versionNo} 版${
          version.id === detail.dungeonVersionId ? "（当前）" : ""
        }`,
        value: version.id,
      }));
  }, [detail, dungeons]);

  const dungeonVersionIdentityById = useMemo(
    () =>
      new Map(
        dungeons.flatMap((dungeon) =>
          dungeon.versions.map((version) => [
            version.id,
            { dungeonName: dungeon.name, versionNo: version.versionNo },
          ] as const),
        ),
      ),
    [dungeons],
  );

  const loadList = async () => {
    try {
      const [scheduleResult, dungeonResult] = await Promise.all([
        api<{ items: ScheduleSummary[] }>(
          `/schedules?includeArchived=${String(showArchived)}`,
        ),
        api<{ items: Dungeon[] }>("/dungeons"),
      ]);
      setSchedules(scheduleResult.items);
      setDungeons(dungeonResult.items);
    } catch (error) {
      onError(error);
    }
  };

  const applyDetail = (next: ScheduleDetail, resetContext = false) => {
    setDetail(next);
    setWaveCount(next.waveCount);
    setSelectedIds(
      next.participants.filter((participant) => participant.isSelected).map((item) => item.id),
    );
    setValidation(null);
    if (resetContext) {
      setGenerationRuns([]);
      setRuleSets([]);
      setRuleSourceText("");
      setRuleMaxSourceChars(2000);
      setRuleParsingEnabled(false);
      setRulePanelOpen(false);
    }
  };

  const rememberEditLock = (lock: EditLock) => {
    setEditLock(lock);
    if (lock.ownedByCurrentUser && lock.token) {
      setScheduleEditLockToken(lock.scheduleId, lock.token);
      editLockRef.current = { scheduleId: lock.scheduleId, token: lock.token };
    }
  };

  const releaseCurrentEditLock = async () => {
    const current = editLockRef.current;
    if (!current) {
      setEditLock(null);
      return;
    }
    editLockRef.current = null;
    setScheduleEditLockToken(current.scheduleId, null);
    setEditLock(null);
    try {
      await api<void>(`/schedules/${current.scheduleId}/lock`, {
        method: "DELETE",
        headers: { "X-Edit-Lock-Token": current.token },
      });
    } catch {
      // The short server lease remains the recovery path if navigation interrupts release.
    }
  };

  const establishEditLock = async (scheduleId: string) => {
    if (!canWrite) {
      setEditLock(await api<EditLock>(`/schedules/${scheduleId}/lock`));
      return;
    }
    try {
      rememberEditLock(
        await api<EditLock>(`/schedules/${scheduleId}/lock`, { method: "POST" }),
      );
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 423) throw error;
      if (error.details.canTakeover === true) {
        rememberEditLock(
          await api<EditLock>(`/schedules/${scheduleId}/lock/takeover`, {
            method: "POST",
          }),
        );
        return;
      }
      setEditLock(await api<EditLock>(`/schedules/${scheduleId}/lock`));
    }
  };

  const acquireEditLock = async () => {
    if (!detail || !canWrite || detail.status === "ARCHIVED") return;
    setEditLockPending(true);
    try {
      await establishEditLock(detail.id);
      onSuccess(
        editLockRef.current?.scheduleId === detail.id
          ? "已获得排表编辑权"
          : "编辑状态已刷新",
      );
    } catch (error) {
      onError(error);
    } finally {
      setEditLockPending(false);
    }
  };

  async function reloadRuleSets(scheduleId: string) {
    const result = await api<ScheduleRuleSetList>(`/schedules/${scheduleId}/rule-sets`);
    setRuleSets(result.items);
    setRuleMaxSourceChars(result.maxSourceChars);
    setRuleParsingEnabled(result.parsingEnabled);
    const active = result.items.find((ruleSet) => ruleSet.id === result.activeRuleSetId);
    setRuleSourceText(active?.sourceText ?? result.items[0]?.sourceText ?? "");
  }

  const leaveSchedule = async () => {
    await releaseCurrentEditLock();
    setDetail(null);
    setGenerationRuns([]);
    setVersions([]);
    setShareUrl("");
    setParticipantPanelOpen(false);
    setUnassignedPanelOpen(false);
    resetEditor();
  };

  const openSchedule = async (scheduleId: string) => {
    try {
      await releaseCurrentEditLock();
      const [schedule, runs, versionResult, ruleSetResult] = await Promise.all([
        api<ScheduleDetail>(`/schedules/${scheduleId}`),
        api<{ items: GenerationRun[] }>(`/schedules/${scheduleId}/generation-runs`),
        api<{ items: ScheduleVersionSummary[] }>(`/schedules/${scheduleId}/versions`),
        api<ScheduleRuleSetList>(`/schedules/${scheduleId}/rule-sets`),
      ]);
      applyDetail(schedule, true);
      const selectedParticipantCount = schedule.participants.filter(
        (participant) => participant.isSelected,
      ).length;
      setParticipantPanelOpen(schedule.participants.length <= 24);
      setUnassignedPanelOpen(selectedParticipantCount <= 24);
      resetEditor();
      setGenerationRuns(runs.items);
      setVersions(versionResult.items);
      setRuleSets(ruleSetResult.items);
      setRuleMaxSourceChars(ruleSetResult.maxSourceChars);
      setRuleParsingEnabled(ruleSetResult.parsingEnabled);
      const activeRuleSet = ruleSetResult.items.find(
        (ruleSet) => ruleSet.id === ruleSetResult.activeRuleSetId,
      );
      setRuleSourceText(activeRuleSet?.sourceText ?? ruleSetResult.items[0]?.sourceText ?? "");
      await establishEditLock(scheduleId);
    } catch (error) {
      onError(error);
    }
  };

  useEffect(() => {
    const token = editLock?.token;
    if (!editLock?.ownedByCurrentUser || !token) return;
    const interval = window.setInterval(() => {
      void api<EditLock>(`/schedules/${editLock.scheduleId}/lock/heartbeat`, {
        method: "POST",
        headers: { "X-Edit-Lock-Token": token },
      })
        .then(rememberEditLock)
        .catch(async () => {
          setScheduleEditLockToken(editLock.scheduleId, null);
          editLockRef.current = null;
          try {
            setEditLock(await api<EditLock>(`/schedules/${editLock.scheduleId}/lock`));
          } catch {
            setEditLock(null);
          }
          onError(new Error("编辑锁已失效，当前排表已切换为只读"));
        });
    }, editLock.heartbeatIntervalSeconds * 1000);
    return () => window.clearInterval(interval);
  }, [editLock?.scheduleId, editLock?.token, editLock?.ownedByCurrentUser]);

  useEffect(
    () => () => {
      const current = editLockRef.current;
      if (!current) return;
      editLockRef.current = null;
      setScheduleEditLockToken(current.scheduleId, null);
      void api<void>(`/schedules/${current.scheduleId}/lock`, {
        method: "DELETE",
        headers: { "X-Edit-Lock-Token": current.token },
        keepalive: true,
      }).catch(() => undefined);
    },
    [],
  );

  const executeEditorOperations = async (
    operations: ScheduleOperation[],
    historyMode: "record" | "undo" | "redo" = "record",
    optimisticDetail?: ScheduleDetail,
  ) => {
    if (!detail || editorPending) return;
    const previousDetail = detail;
    setEditorPending(true);
    if (optimisticDetail) setDetail(optimisticDetail);
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
      if (optimisticDetail) setDetail(previousDetail);
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
    if (String(over.id) === "unassigned-pool") {
      const isAssigned = allScheduleSlots(detail).some(
        (slot) => slot.participantId === participantId,
      );
      if (!isAssigned) return;
      const operations: ScheduleOperation[] = [
        { type: "UNASSIGN_PARTICIPANT", participantId },
      ];
      await executeEditorOperations(
        operations,
        "record",
        applyOptimisticAssignment(detail, operations),
      );
      return;
    }
    const slotId = String(over.id).replace(/^slot:/, "");
    const target = allScheduleSlots(detail).find((slot) => slot.id === slotId);
    if (!target || target.participantId === participantId) return;
    const operations = buildDropOperations(detail, participantId, target.id);
    if (operations.length === 0) return;
    await executeEditorOperations(operations, "record", applyOptimisticAssignment(detail, operations));
  };

  useEffect(() => {
    void loadList();
  }, [showArchived]);

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
      await releaseCurrentEditLock();
      applyDetail(created, true);
      setParticipantPanelOpen(true);
      setUnassignedPanelOpen(true);
      resetEditor();
      setVersions([]);
      await establishEditLock(created.id);
      onSuccess("排表已创建");
    } catch (error) {
      onError(error);
    }
  };

  const changeArchiveState = async (action: "archive" | "restore") => {
    if (!detail) return;
    setLifecyclePending(true);
    try {
      const next = await api<ScheduleDetail>(`/schedules/${detail.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ baseRevision: detail.revision }),
      });
      applyDetail(next);
      await reloadRuleSets(next.id);
      await loadList();
      onSuccess(action === "archive" ? "排表已归档" : "排表已恢复为草稿");
    } catch (error) {
      onError(error);
    } finally {
      setLifecyclePending(false);
    }
  };

  const permanentlyDeleteSchedule = async () => {
    if (!detail) return;
    setLifecyclePending(true);
    try {
      await api<void>(`/schedules/${detail.id}`, {
        method: "DELETE",
        body: JSON.stringify({
          baseRevision: detail.revision,
          confirmationName: deleteConfirmation,
        }),
      });
      setScheduleEditLockToken(detail.id, null);
      editLockRef.current = null;
      setEditLock(null);
      setDeleteOpen(false);
      setDeleteConfirmation("");
      setDetail(null);
      setVersions([]);
      resetEditor();
      await loadList();
      onSuccess("未发布草稿已永久删除");
    } catch (error) {
      onError(error);
    } finally {
      setLifecyclePending(false);
    }
  };

  const updateWaves = async (confirmWaveReduction = false) => {
    if (!detail) return;
    try {
      const next = await api<ScheduleDetail>(`/schedules/${detail.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: detail.revision,
          waveCount,
          confirmWaveReduction,
        }),
      });
      applyDetail(next);
      await reloadRuleSets(next.id);
      await loadList();
      onSuccess("排表波数已更新");
    } catch (error) {
      if (
        !confirmWaveReduction &&
        error instanceof ApiError &&
        error.code === "WAVE_REDUCTION_CONFIRMATION_REQUIRED"
      ) {
        const waveNos = Array.isArray(error.details.waveNos)
          ? error.details.waveNos.join("、")
          : "末尾";
        Modal.confirm({
          title: "确认删除已有内容的波次？",
          content: `第 ${waveNos} 波包含已分配角色或锁定位置，继续后这些内容会被移除。`,
          okText: "确认缩减",
          cancelText: "取消",
          okButtonProps: { danger: true },
          onOk: () => updateWaves(true),
        });
        return;
      }
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
      await reloadRuleSets(next.id);
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
      await reloadRuleSets(next.id);
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
      await releaseCurrentEditLock();
      applyDetail(copied, true);
      await establishEditLock(copied.id);
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
    setGenerationFailure(null);
    try {
      const response = await api<GenerationResponse>(`/schedules/${detail.id}/generate`, {
        method: "POST",
        body: JSON.stringify({
          baseRevision: detail.revision,
          preserveLocks: generationPreserveLocks,
          randomSeed: generationSeed,
          timeLimitSeconds: generationTimeLimit,
          expectedRuleSetId: detail.activeRuleSetId,
        }),
      });
      applyDetail(response.schedule);
      setGenerationRuns((current) => [
        response.run,
        ...current.filter((run) => run.id !== response.run.id),
      ]);
      setGenerationOpen(false);
      await loadList();
      onSuccess(
        response.run.status === "PARTIAL"
          ? "已生成部分排表，请查看未分配原因"
          : "自动排表已生成",
      );
    } catch (error) {
      if (error instanceof ApiError) {
        setGenerationFailure(error);
        if (error.code === "SCHEDULE_GENERATION_TIMEOUT") {
          const suggestedTimeLimit = Number(error.details.suggestedTimeLimitSeconds);
          const suggestedSeed = Number(error.details.suggestedRandomSeed);
          if (Number.isInteger(suggestedTimeLimit) && suggestedTimeLimit >= 1) {
            setGenerationTimeLimit(Math.min(60, suggestedTimeLimit));
          }
          if (Number.isInteger(suggestedSeed) && suggestedSeed >= 0) {
            setGenerationSeed(Math.min(2_147_483_647, suggestedSeed));
          }
        }
      }
      onError(error);
    } finally {
      setGenerationPending(false);
    }
  };

  const openGeneration = async () => {
    if (!detail) return;
    try {
      const report = await api<ValidationReport>(`/schedules/${detail.id}/validate`, {
        method: "POST",
        body: JSON.stringify({ baseRevision: detail.revision }),
      });
      setValidation(report);
      await loadList();
      if (report.summary.error > 0) {
        onError(new Error(`预检查发现 ${report.summary.error} 个错误，请先处理后再生成`));
        return;
      }
      setGenerationFailure(null);
      setGenerationOpen(true);
    } catch (error) {
      onError(error);
    }
  };

  const saveMetadata = async () => {
    if (!detail || !metadataName.trim()) return;
    try {
      const next = await api<ScheduleDetail>(`/schedules/${detail.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: detail.revision,
          name: metadataName.trim(),
          note: metadataNote.trim() || null,
        }),
      });
      applyDetail(next);
      setMetadataOpen(false);
      await loadList();
      onSuccess("排表信息已更新");
    } catch (error) {
      onError(error);
    }
  };

  const refreshRuleState = async () => {
    if (!detail) return;
    const [schedule, result] = await Promise.all([
      api<ScheduleDetail>(`/schedules/${detail.id}`),
      api<ScheduleRuleSetList>(`/schedules/${detail.id}/rule-sets`),
    ]);
    applyDetail(schedule);
    setRuleSets(result.items);
    setRuleMaxSourceChars(result.maxSourceChars);
    setRuleParsingEnabled(result.parsingEnabled);
  };

  const parseRuleSource = async () => {
    if (!detail || !ruleSourceText.trim()) return;
    setRulePending(true);
    try {
      const parsed = await api<ScheduleRuleSet>(`/schedules/${detail.id}/rule-sets/parse`, {
        method: "POST",
        body: JSON.stringify({
          baseRevision: detail.revision,
          sourceText: ruleSourceText.trim(),
        }),
      });
      setRuleSets((current) => [parsed, ...current.filter((item) => item.id !== parsed.id)]);
      onSuccess(
        parsed.issues.length
          ? "解析完成，请先处理歧义或不支持项"
          : "解析完成，请确认结构化规则",
      );
    } catch (error) {
      onError(describeRuleParseError(error));
    } finally {
      setRulePending(false);
    }
  };

  const confirmRuleSet = async (ruleSet: ScheduleRuleSet) => {
    if (!detail) return;
    setRulePending(true);
    try {
      await api<ScheduleRuleSetMutationResponse>(
        `/schedules/${detail.id}/rule-sets/${ruleSet.id}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({
            baseRevision: detail.revision,
            sourceHash: ruleSet.sourceHash,
            contextHash: ruleSet.contextHash,
          }),
        },
      );
      await refreshRuleState();
      onSuccess("本次排表要求已确认，将在自动排表时生效");
    } catch (error) {
      onError(error);
    } finally {
      setRulePending(false);
    }
  };

  const clearActiveRuleSet = async () => {
    if (!detail) return;
    setRulePending(true);
    try {
      await api<ScheduleRuleSetMutationResponse>(
        `/schedules/${detail.id}/rule-sets/clear`,
        {
          method: "POST",
          body: JSON.stringify({ baseRevision: detail.revision }),
        },
      );
      await refreshRuleState();
      onSuccess("已停用本次排表要求");
    } catch (error) {
      onError(error);
    } finally {
      setRulePending(false);
    }
  };

  const openPublish = async () => {
    if (!detail) return;
    setPublishPending(true);
    try {
      const check = await api<SchedulePublicationCheck>(
        `/schedules/${detail.id}/publication-check`,
        {
          method: "POST",
          body: JSON.stringify({ baseRevision: detail.revision }),
        },
      );
      setPublicationCheck(check);
      setConfirmPublishWarnings(false);
      setPublishOpen(true);
    } catch (error) {
      onError(error);
    } finally {
      setPublishPending(false);
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
      setPublicationCheck(null);
      resetEditor();
      await loadList();
      onSuccess(`排表已发布为第 ${response.version.versionNo} 版`);
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
      await reloadRuleSets(restored.id);
      resetEditor();
      setHistoryOpen(false);
      await loadList();
      onSuccess(`已从发布版本第 ${versionNo} 版恢复为草稿`);
    } catch (error) {
      onError(error);
    }
  };

  const confirmRestoreVersion = (versionNo: number) => {
    Modal.confirm({
      title: `恢复发布版本第 ${versionNo} 版？`,
      content: "当前草稿布局会被该发布版本替换；发布历史不会被删除。",
      okText: "确认恢复",
      cancelText: "取消",
      onOk: () => restoreVersion(versionNo),
    });
  };

  const previewPublishedVersion = async (version: ScheduleVersionSummary) => {
    if (!detail) return;
    setVersionActionPending(true);
    try {
      setVersionPreview(
        await api<ScheduleVersionView>(
          `/schedules/${detail.id}/versions/${version.versionNo}`,
        ),
      );
    } catch (error) {
      onError(error);
    } finally {
      setVersionActionPending(false);
    }
  };

  const copyPublishedVersion = async () => {
    if (!detail || !copyVersionTarget || !copyVersionName.trim()) return;
    setVersionActionPending(true);
    try {
      const copied = await api<ScheduleDetail>(
        `/schedules/${detail.id}/versions/${copyVersionTarget.versionNo}/copy-as-draft`,
        {
          method: "POST",
          body: JSON.stringify({ name: copyVersionName }),
        },
      );
      setCopyVersionTarget(null);
      setHistoryOpen(false);
      await releaseCurrentEditLock();
      applyDetail(copied, true);
      resetEditor();
      setVersions([]);
      await loadList();
      await establishEditLock(copied.id);
      onSuccess(`已从发布版本第 ${copyVersionTarget.versionNo} 版创建新草稿`);
    } catch (error) {
      onError(error);
    } finally {
      setVersionActionPending(false);
    }
  };

  const openShareManager = async (version: ScheduleVersionSummary) => {
    setShareVersion(version);
    setShareUrl("");
    setSharePending(true);
    try {
      const result = await api<{ items: ShareLinkView[] }>(
        `/schedule-versions/${version.id}/share-links`,
      );
      setShareLinks(result.items);
    } catch (error) {
      setShareVersion(null);
      onError(error);
    } finally {
      setSharePending(false);
    }
  };

  const createShare = async () => {
    if (!shareVersion) return;
    setSharePending(true);
    try {
      const link = await api<ShareLinkCreated>(`/schedule-versions/${shareVersion.id}/share-links`, {
        method: "POST",
        body: JSON.stringify({ expiresInDays: shareExpiryDays }),
      });
      setShareUrl(`${window.location.origin}/share/${link.token}`);
      const result = await api<{ items: ShareLinkView[] }>(
        `/schedule-versions/${shareVersion.id}/share-links`,
      );
      setShareLinks(result.items);
    } catch (error) {
      onError(error);
    } finally {
      setSharePending(false);
    }
  };

  const revokeShare = async (shareLinkId: string) => {
    if (!shareVersion) return;
    setSharePending(true);
    try {
      await api<void>(`/share-links/${shareLinkId}`, { method: "DELETE" });
      const result = await api<{ items: ShareLinkView[] }>(
        `/schedule-versions/${shareVersion.id}/share-links`,
      );
      setShareLinks(result.items);
      onSuccess("分享链接已撤销");
    } catch (error) {
      onError(error);
    } finally {
      setSharePending(false);
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
      await reloadRuleSets(next.id);
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
          <Space>
            <Typography.Text type="secondary">显示已归档</Typography.Text>
            <Switch checked={showArchived} onChange={setShowArchived} />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!canWrite}
              onClick={() => setCreateOpen(true)}
            >
              新建排表
            </Button>
          </Space>
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
                      <Tag
                        color={
                          schedule.status === "DRAFT"
                            ? "orange"
                            : schedule.status === "PUBLISHED"
                              ? "green"
                              : "default"
                        }
                      >
                        {SCHEDULE_STATUS_LABELS[schedule.status]}
                      </Tag>
                    </Space>
                    <Typography.Text type="secondary">
                      {describeDungeonVersion(
                        dungeonVersionIdentityById.get(schedule.dungeonVersionId),
                        schedule.dungeonVersionId,
                      )} · {schedule.waveCount} 波 · 修订 {schedule.revision}
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
  const selectedPlayerIds = new Set(
    selectedParticipants.map((participant) => participant.playerIdSnapshot),
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
  const ownsEditLock = Boolean(editLock?.ownedByCurrentUser);
  const canEditSchedule = canWrite && detail.status !== "ARCHIVED" && ownsEditLock;
  const canCreateContent = canWrite;
  const canGenerateSchedule = canEditSchedule && hasPermission("SCHEDULE_GENERATE");
  const canPublishSchedule = canEditSchedule && hasPermission("SCHEDULE_PUBLISH");
  const canExportSchedule = hasPermission("SCHEDULE_EXPORT");
  const canManageShare = hasPermission("SHARE_MANAGE");
  const canManageLifecycle = hasPermission("SCHEDULE_PUBLISH") && ownsEditLock;
  const canPermanentlyDelete =
    detail.status === "DRAFT" &&
    versions.length === 0 &&
    hasPermission("SCHEDULE_DELETE") &&
    ownsEditLock;
  const activeRuleSet = ruleSets.find((ruleSet) => ruleSet.id === detail.activeRuleSetId);
  const parsedRuleSet = ruleSets.find((ruleSet) => ruleSet.status === "PARSED");
  const latestGeneration = generationRuns[0] ?? null;
  const previousGeneration = generationRuns[1] ?? null;
  const filteredUnassignedParticipants = unassignedParticipants
    .filter(
      (participant) =>
        unassignedRoleFilter === "ALL" ||
        participant.roleTypeSnapshot === unassignedRoleFilter,
    )
    .slice()
    .sort((left, right) => {
      if (unassignedSort === "PLAYER") {
        return left.playerNameSnapshot.localeCompare(right.playerNameSnapshot, "zh-CN");
      }
      if (unassignedSort === "SCORE_DESC") {
        const leftScore = Number(
          left.roleTypeSnapshot === "DAMAGE"
            ? left.damageScoreSnapshot
            : left.bufferScoreSnapshot,
        );
        const rightScore = Number(
          right.roleTypeSnapshot === "DAMAGE"
            ? right.damageScoreSnapshot
            : right.bufferScoreSnapshot,
        );
        return rightScore - leftScore;
      }
      return detail.participants.indexOf(left) - detail.participants.indexOf(right);
    });
  const focusValidationIssue = (issue: ValidationIssue) => {
    const waveNo = Number(issue.message_params.waveNo);
    if (!Number.isInteger(waveNo) || waveNo < 1 || waveNo > detail.waveCount) return;
    setViewMode("wave");
    setSelectedWaveNo(waveNo);
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-wave-no="${waveNo}"]`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  };

  return (
    <section>
      <div className="section-heading schedule-detail-heading">
        <div>
          <Button
            type="link"
            className="schedule-back"
            onClick={() => void leaveSchedule()}
          >
            ← 返回排表列表
          </Button>
          <Typography.Title level={2}>{detail.name}</Typography.Title>
          <Typography.Text type="secondary">
            {describeDungeonVersion(
              dungeonVersionIdentityById.get(detail.dungeonVersionId),
              detail.dungeonVersionId,
            )} · {detail.waveCount} 波 · 修订 {detail.revision} ·{" "}
            {SCHEDULE_STATUS_LABELS[detail.status]}
          </Typography.Text>
        </div>
        <Space wrap size={6} className="schedule-action-bar">
          <Button size="small" icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
            发布历史 {versions.length ? `(${versions.length})` : ""}
          </Button>
          <Button
            size="small"
            icon={<CheckCircleOutlined />}
            disabled={hasUnsavedChanges || detail.status === "ARCHIVED"}
            onClick={() => void validate()}
          >
            运行预检查
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            disabled={!canGenerateSchedule || hasUnsavedChanges || detail.status === "ARCHIVED"}
            onClick={() => void openGeneration()}
          >
            {detail.waves.some((wave) =>
              wave.teams.some((team) => team.slots.some((slot) => slot.participantId)),
            )
              ? "重新生成"
              : "自动排表"}
          </Button>
          <Button
            size="small"
            icon={<SendOutlined />}
            loading={publishPending}
            disabled={
              !canPublishSchedule ||
              hasUnsavedChanges ||
              detail.status === "ARCHIVED" ||
              detail.status === "PUBLISHED"
            }
            onClick={() => void openPublish()}
          >
            发布排表
          </Button>
          <Dropdown
            trigger={["click"]}
            menu={{
              onClick: ({ key }) => {
                if (key === "metadata") {
                  setMetadataName(detail.name);
                  setMetadataNote(detail.note ?? "");
                  setMetadataOpen(true);
                } else if (key === "preferences") {
                  openPreferences();
                } else if (key === "sync") {
                  void previewSync();
                } else if (key === "copy") {
                  setCopyName(`${detail.name} - 副本`);
                  setCopyTargetVersionId(detail.dungeonVersionId);
                  setCopyWaveCount(detail.waveCount);
                  setCopyPreview(null);
                  setCopyOpen(true);
                } else if (key === "archive") {
                  Modal.confirm({
                    title: "归档当前排表？",
                    content: "归档后排表将变为只读，仍可查看历史和导出。",
                    okText: "确认归档",
                    cancelText: "取消",
                    onOk: () => changeArchiveState("archive"),
                  });
                } else if (key === "restore") {
                  Modal.confirm({
                    title: "恢复为可编辑草稿？",
                    okText: "确认恢复",
                    cancelText: "取消",
                    onOk: () => changeArchiveState("restore"),
                  });
                } else if (key === "delete") {
                  setDeleteConfirmation("");
                  setDeleteOpen(true);
                }
              },
              items: [
                { key: "metadata", label: "排表名称与备注", disabled: !canEditSchedule },
                { key: "preferences", label: "玩家波次与偏好", disabled: !canEditSchedule || hasUnsavedChanges },
                { key: "sync", label: "同步最新角色", disabled: !canEditSchedule || hasUnsavedChanges },
                { key: "copy", label: "复制排表", disabled: !canCreateContent || hasUnsavedChanges },
                ...(detail.status === "DRAFT" && canExportSchedule
                  ? [
                      { type: "divider" as const },
                      { key: "image", label: <a href={`/api/v1/schedules/${detail.id}/exports/image`}>导出草稿长图</a> },
                      { key: "excel", label: <a href={`/api/v1/schedules/${detail.id}/exports/excel`}>导出草稿 Excel</a> },
                      { key: "text", label: <a href={`/api/v1/schedules/${detail.id}/exports/text`}>导出草稿文本</a> },
                    ]
                  : []),
                { type: "divider" as const },
                detail.status === "ARCHIVED"
                  ? { key: "restore", label: "恢复草稿", disabled: !canManageLifecycle }
                  : { key: "archive", label: "归档排表", disabled: !canManageLifecycle || hasUnsavedChanges },
                ...(canPermanentlyDelete
                  ? [{ key: "delete", label: <Typography.Text type="danger">永久删除</Typography.Text>, danger: true }]
                  : []),
              ],
            }}
          >
            <Button size="small" icon={<MoreOutlined />} loading={lifecyclePending}>
              更多 <DownOutlined />
            </Button>
          </Dropdown>
        </Space>
      </div>

      {!canEditSchedule ? (
        <Alert
          className="schedule-panel schedule-lock-alert"
          type="info"
          showIcon
          title={
            detail.status === "ARCHIVED"
              ? "已归档排表以只读方式展示"
              : !canWrite
              ? userRole === "VIEWER"
                ? "Viewer 账号以只读方式查看排表"
                : "当前角色以只读方式查看排表"
              : editLock?.held
                ? `当前由 ${editLock.holderUsername ?? "其他账号"} 编辑`
                : "当前未持有编辑锁"
          }
          description={
            detail.status === "ARCHIVED"
              ? "仍可查看发布历史和导出；具备发布权限时可以恢复为草稿。"
              : editLock?.expiresAt && editLock.held
              ? `租约预计于 ${new Date(editLock.expiresAt).toLocaleTimeString()} 到期；到期后重新进入可自动接管。`
              : "查看、预检查、历史预览和导出仍可使用。"
          }
          action={
            canWrite && detail.status !== "ARCHIVED" ? (
              <Button size="small" loading={editLockPending} onClick={() => void acquireEditLock()}>
                {editLock?.canTakeover ? "接管编辑" : editLock?.held ? "刷新编辑状态" : "获取编辑权"}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Alert
          className="schedule-panel schedule-lock-alert"
          type="success"
          showIcon
          title="已获得此排表的单编辑会话锁"
          description="页面会自动发送心跳；离开排表或租约失效后，写操作将立即切换为只读。"
        />
      )}

      {hasUnsavedChanges ? (
        <Alert
          className="schedule-panel"
          type="warning"
          showIcon
          title="当前有尚未保存的排表设置"
          description="请先保存参团角色选择或更新波数，再进行复制、角色同步和预检查。"
        />
      ) : null}

      <Card
        title="本次排表要求"
        className="schedule-panel schedule-rule-card"
        size="small"
        extra={
          <Space size={4}>
            {activeRuleSet ? (
              <>
              <Tag color="green">已确认 {activeRuleSet.parsedRules.length} 条</Tag>
              <Button
                type="link"
                size="small"
                danger
                loading={rulePending}
                disabled={!canGenerateSchedule || hasUnsavedChanges}
                onClick={() => void clearActiveRuleSet()}
              >
                停用
              </Button>
              </>
            ) : (
              <Tag>未启用</Tag>
            )}
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => setRulePanelOpen((open) => !open)}
            >
              {rulePanelOpen ? "收起" : "配置"}
            </Button>
          </Space>
        }
      >
        {!rulePanelOpen ? (
          <Typography.Text type="secondary">
            {activeRuleSet
              ? activeRuleSet.sourceText
              : "可用自然语言补充只对当前排表生效的硬规则和软目标。"}
          </Typography.Text>
        ) : (
          <>
        <Typography.Paragraph type="secondary" className="compact-description">
          {ruleParsingEnabled
            ? "DeepSeek 仅把本次要求解析成白名单规则；确认后由 OR-Tools 执行，不会修改副本版本。"
            : "当前环境未启用自然语言规则解析，请联系管理员配置后使用。"}
        </Typography.Paragraph>
        <Input.TextArea
          value={ruleSourceText}
          maxLength={ruleMaxSourceChars}
          showCount
          rows={3}
          placeholder="例如：韩亚尽量安排在前 6 波；剑来和点评不能在同一波。"
          disabled={!canGenerateSchedule || !ruleParsingEnabled}
          onChange={(event) => setRuleSourceText(event.target.value)}
        />
        <div className="schedule-rule-actions">
          <Button
            size="small"
            type="primary"
            loading={rulePending}
            disabled={
              !canGenerateSchedule ||
              !ruleParsingEnabled ||
              hasUnsavedChanges ||
              !ruleSourceText.trim()
            }
            onClick={() => void parseRuleSource()}
          >
            解析要求
          </Button>
          {activeRuleSet ? (
            <Typography.Text type="secondary">
              当前生效版本由 {activeRuleSet.modelName} 解析；修改文字后需重新解析并确认。
            </Typography.Text>
          ) : null}
        </div>
        {parsedRuleSet ? (
          <div className="schedule-rule-preview">
            <div className="schedule-rule-preview-heading">
              <Typography.Text strong>解析预览</Typography.Text>
              <Space size={4}>
                <Tag color="red">
                  硬规则 {parsedRuleSet.parsedRules.filter((rule) => rule.enforcement === "HARD").length}
                </Tag>
                <Tag color="blue">
                  软目标 {parsedRuleSet.parsedRules.filter((rule) => rule.enforcement === "SOFT").length}
                </Tag>
              </Space>
            </div>
            <Space wrap size={[4, 4]}>
              {parsedRuleSet.parsedRules.map((rule) => (
                <Tag
                  key={rule.candidateId}
                  color={rule.enforcement === "HARD" ? "red" : "blue"}
                >
                  {RULE_TYPE_LABELS[rule.type] ?? rule.type} · {rule.explanation}
                </Tag>
              ))}
            </Space>
            {parsedRuleSet.issues.map((issue, index) => (
              <Alert
                key={`${issue.code}-${index}`}
                type="warning"
                showIcon
                title={RULE_ISSUE_LABELS[issue.code] ?? "规则无法确认"}
                description={describeRuleResolutionIssue(issue)}
              />
            ))}
            <Button
              size="small"
              type="primary"
              loading={rulePending}
              disabled={
                !canGenerateSchedule ||
                hasUnsavedChanges ||
                Boolean(parsedRuleSet.issues.length) ||
                !parsedRuleSet.parsedRules.length
              }
              onClick={() => void confirmRuleSet(parsedRuleSet)}
            >
              确认并用于自动排表
            </Button>
          </div>
        ) : null}
          </>
        )}
      </Card>

      <Card className="schedule-panel schedule-overview-card" size="small">
        <div className="schedule-overview-grid">
          <Statistic title="参团角色" value={selectedParticipants.length} />
          <Statistic title="已安排" value={assignedParticipantIds.size} />
          <Statistic title="C" value={damageCount} />
          <Statistic title="奶" value={selectedParticipants.length - damageCount} />
          <div className="wave-count-control">
            <Typography.Text type="secondary">波数</Typography.Text>
            <Space.Compact>
              <InputNumber
                min={1}
                max={50}
                size="small"
                disabled={!canEditSchedule}
                value={waveCount}
                onChange={(value) => setWaveCount(value ?? 1)}
              />
              <Button
                size="small"
                icon={<SettingOutlined />}
                disabled={!canEditSchedule}
                onClick={() => void updateWaves()}
              >
                更新波数
              </Button>
            </Space.Compact>
          </div>
        </div>
      </Card>

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
                  action={
                    Number.isInteger(Number(issue.message_params.waveNo)) ? (
                      <Button size="small" type="link" onClick={() => focusValidationIssue(issue)}>
                        定位到波次
                      </Button>
                    ) : undefined
                  }
                />
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有问题" />
          )}
        </Card>
      ) : null}

      {latestGeneration ? (
        <GenerationSummary
          run={latestGeneration}
          previousRun={previousGeneration}
          participants={detail.participants}
          currentRevision={detail.revision}
          runCount={generationRuns.length}
          canTryAlternative={canGenerateSchedule && !hasUnsavedChanges}
          onOpenHistory={() => setGenerationHistoryOpen(true)}
          onTryAlternative={() => {
            setGenerationSeed((seed) => (seed >= 2_147_483_647 ? 1 : seed + 1));
            void openGeneration();
          }}
        />
      ) : null}

      <Card
        title={`参团角色 · 已选 ${selectedParticipants.length}/${detail.participants.length}`}
        className="schedule-panel participant-panel"
        size="small"
        extra={
          <Space size={4}>
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => setParticipantPanelOpen((open) => !open)}
            >
              {participantPanelOpen ? "收起角色选择" : "展开角色选择"}
            </Button>
            <Button
              size="small"
              disabled={!canEditSchedule || !participantSelectionDirty}
              onClick={() => void saveParticipants()}
            >
              保存选择
            </Button>
          </Space>
        }
      >
        {participantPanelOpen ? (
          <Checkbox.Group
            className="participant-checkbox-group"
            disabled={!canEditSchedule}
            value={selectedIds}
            onChange={(values) => setSelectedIds(values as string[])}
          >
            <div className="participant-grid">
              {detail.participants.map((participant) => (
                <Checkbox value={participant.id} key={participant.id} className="participant-option">
                  <ScheduleParticipantLabel participant={participant} />
                </Checkbox>
              ))}
            </div>
          </Checkbox.Group>
        ) : (
          <Typography.Text type="secondary">
            候选角色已收起，需要调整参团名单时再展开。
          </Typography.Text>
        )}
      </Card>

      <Card className="schedule-panel editor-toolbar">
        <div className="editor-toolbar-content">
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
            disabled={!canEditSchedule || !undoStack.length || editorPending}
            onClick={() => void undo()}
          >
            撤销
          </Button>
          <Button
            icon={<RedoOutlined />}
            disabled={!canEditSchedule || !redoStack.length || editorPending}
            onClick={() => void redo()}
          >
            恢复
          </Button>
          <Typography.Text type="secondary">拖动角色到空位，拖到其他角色上可直接交换</Typography.Text>
        </Space>
        <div className="wave-navigator" aria-label="波次导航">
          {detail.waves.map((wave) => {
            const assigned = wave.teams.flatMap((team) => team.slots).filter((slot) => slot.participantId).length;
            const capacity = wave.teams.reduce((sum, team) => sum + team.memberCountSnapshot, 0);
            return (
              <Button
                key={wave.id}
                size="small"
                type={viewMode === "wave" && selectedWaveNo === wave.waveNo ? "primary" : "text"}
                className="wave-nav-button"
                title={`第 ${wave.waveNo} 波 · ${assigned}/${capacity}`}
                onClick={() => {
                  setViewMode("wave");
                  setSelectedWaveNo(wave.waveNo);
                }}
              >
                <span className={`wave-nav-dot ${assigned === capacity ? "complete" : assigned ? "partial" : "empty"}`} />
                {wave.waveNo}
              </Button>
            );
          })}
        </div>
        </div>
      </Card>

      <DndContext sensors={sensors} onDragEnd={(event) => void onDragEnd(event)}>
        <Card
          size="small"
          title={`未分配角色 · ${unassignedParticipants.length}`}
          className="schedule-panel unassigned-panel"
          extra={
            unassignedParticipants.length ? (
              <Button
                type="text"
                size="small"
                onClick={() => setUnassignedPanelOpen((open) => !open)}
              >
                {unassignedPanelOpen ? "收起" : "展开"}
              </Button>
            ) : null
          }
        >
          {unassignedPanelOpen && unassignedParticipants.length ? (
            <>
              <div className="unassigned-toolbar">
                <Segmented
                  size="small"
                  value={unassignedRoleFilter}
                  onChange={(value) => setUnassignedRoleFilter(value as "ALL" | "DAMAGE" | "BUFFER")}
                  options={[
                    { label: "全部", value: "ALL" },
                    { label: "C", value: "DAMAGE" },
                    { label: "奶", value: "BUFFER" },
                  ]}
                />
                <Select
                  size="small"
                  value={unassignedSort}
                  onChange={setUnassignedSort}
                  options={[
                    { label: "按人员顺序", value: "ORDER" },
                    { label: "按数值从高到低", value: "SCORE_DESC" },
                    { label: "按玩家名称", value: "PLAYER" },
                  ]}
                  style={{ width: 154 }}
                />
                <Typography.Text type="secondary">
                  可将队伍中的角色拖回这里
                </Typography.Text>
              </div>
              <ScheduleUnassignedDropZone active={canEditSchedule && !editorPending}>
              {filteredUnassignedParticipants.map((participant) => (
                <ScheduleDraggableParticipant
                  key={participant.id}
                  participant={participant}
                  disabled={!canEditSchedule || participant.isLocked || editorPending}
                />
              ))}
              {!filteredUnassignedParticipants.length ? (
                <Typography.Text type="secondary">当前筛选下没有角色</Typography.Text>
              ) : null}
              </ScheduleUnassignedDropZone>
            </>
          ) : (
            <Typography.Text type="secondary">
              {unassignedParticipants.length
                ? "角色池已收起，展开后可拖入队伍。"
                : "所有参团角色都已安排"}
            </Typography.Text>
          )}
        </Card>
        <div className="wave-list">
          {visibleWaves.map((wave) => (
            <ScheduleEditorWave
              key={wave.id}
              wave={wave}
              participantsById={participantsById}
              disabled={!canEditSchedule || editorPending}
              onOperation={(operation) => void executeEditorOperations([operation])}
            />
          ))}
        </div>
      </DndContext>

      <Modal
        title="发布排表"
        open={publishOpen}
        onCancel={() => {
          setPublishOpen(false);
          setPublicationCheck(null);
        }}
        onOk={() => void publish()}
        okText="确认发布"
        confirmLoading={publishPending}
        okButtonProps={{
          disabled:
            !canPublishSchedule ||
            !publicationCheck?.publishable ||
            Boolean(publicationCheck.summary.warning && !confirmPublishWarnings),
        }}
        width={720}
      >
        <Alert
          type="info"
          showIcon
          title="发布后会保存不可变快照"
          description="以后继续编辑会自动回到草稿状态，已发布版本及其导出内容不会改变。"
        />
        {publicationCheck ? (
          <>
            <Space wrap className="publish-check-summary">
              <Tag color="red">错误 {publicationCheck.summary.error}</Tag>
              <Tag color="orange">警告 {publicationCheck.summary.warning}</Tag>
              <Tag color="blue">提示 {publicationCheck.summary.info}</Tag>
            </Space>
            <div className="issue-list publish-issue-list">
              {publicationCheck.issues.map((issue) => (
                <Alert
                  key={`${issue.code}-${JSON.stringify(issue.message_params)}`}
                  type={issue.severity === "ERROR" ? "error" : "warning"}
                  showIcon
                  title={ISSUE_LABELS[issue.code] ?? issue.code}
                  description={describeIssue(issue)}
                />
              ))}
            </div>
            {publicationCheck.summary.warning ? (
              <Checkbox
                className="publish-warning-confirm"
                checked={confirmPublishWarnings}
                onChange={(event) => setConfirmPublishWarnings(event.target.checked)}
              >
                我已查看以上非阻断警告，仍要发布
              </Checkbox>
            ) : null}
          </>
        ) : null}
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
                title={`第 ${version.versionNo} 版`}
                extra={new Date(version.publishedAt).toLocaleString()}
              >
                <Space wrap>
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    loading={versionActionPending}
                    onClick={() => void previewPublishedVersion(version)}
                  >
                    预览
                  </Button>
                  <Button
                    size="small"
                    icon={<HistoryOutlined />}
                    disabled={!canPublishSchedule}
                    onClick={() => confirmRestoreVersion(version.versionNo)}
                  >
                    恢复为草稿
                  </Button>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    disabled={!canCreateContent}
                    onClick={() => {
                      setCopyVersionTarget(version);
                      setCopyVersionName(`${detail.name} · 第 ${version.versionNo} 版副本`);
                    }}
                  >
                    复制为新草稿
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={!canExportSchedule}
                    href={`/api/v1/schedule-versions/${version.id}/exports/image`}
                  >
                    长图
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={!canExportSchedule}
                    href={`/api/v1/schedule-versions/${version.id}/exports/excel`}
                  >
                    Excel
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={!canExportSchedule}
                    href={`/api/v1/schedule-versions/${version.id}/exports/text`}
                  >
                    文本
                  </Button>
                  <Button
                    size="small"
                    icon={<SendOutlined />}
                    disabled={!canManageShare}
                    onClick={() => void openShareManager(version)}
                  >
                    管理分享链接
                  </Button>
                </Space>
                <Typography.Text type="secondary" className="version-hash">
                  来源修订 {version.sourceRevision} · 摘要 {version.snapshotHash.slice(0, 12)}
                </Typography.Text>
              </Card>
            ))}
          </div>
        ) : (
          <Empty description="尚未发布任何版本" />
        )}
      </Modal>

      <Modal
        title={
          versionPreview ? `发布版本第 ${versionPreview.versionNo} 版预览` : "发布版本预览"
        }
        open={versionPreview !== null}
        onCancel={() => setVersionPreview(null)}
        footer={<Button onClick={() => setVersionPreview(null)}>关闭</Button>}
        width={1100}
      >
        {versionPreview ? <ScheduleSnapshotPreview schedule={versionPreview.snapshot} /> : null}
      </Modal>

      <Modal
        title={
          copyVersionTarget
            ? `复制发布版本第 ${copyVersionTarget.versionNo} 版`
            : "复制发布版本"
        }
        open={copyVersionTarget !== null}
        onCancel={() => setCopyVersionTarget(null)}
        onOk={() => void copyPublishedVersion()}
        okText="创建新草稿"
        confirmLoading={versionActionPending}
        okButtonProps={{ disabled: !canCreateContent || !copyVersionName.trim() }}
      >
        <Typography.Paragraph type="secondary">
          新草稿会完整复制该不可变版本的人员快照、队伍位置、核心角色和锁定状态，原版本不会改变。
        </Typography.Paragraph>
        <Input
          value={copyVersionName}
          maxLength={160}
          onChange={(event) => setCopyVersionName(event.target.value)}
          placeholder="新草稿名称"
        />
      </Modal>

      <Modal
        title={
          shareVersion ? `发布版本第 ${shareVersion.versionNo} 版 · 分享链接` : "分享链接"
        }
        open={shareVersion !== null}
        onCancel={() => {
          setShareVersion(null);
          setShareUrl("");
          setShareLinks([]);
        }}
        footer={<Button onClick={() => setShareVersion(null)}>关闭</Button>}
        width={760}
      >
        <Typography.Paragraph type="secondary">
          明文链接仅在创建时展示一次。列表只保留状态和有效期，服务端不会保存明文令牌。
        </Typography.Paragraph>
        <Space wrap className="share-create-row">
          <Select
            value={shareExpiryDays ?? "never"}
            onChange={(value) => setShareExpiryDays(value === "never" ? null : Number(value))}
            options={[
              { label: "7 天有效", value: 7 },
              { label: "30 天有效", value: 30 },
              { label: "90 天有效", value: 90 },
              { label: "永不过期", value: "never" },
            ]}
            style={{ width: 150 }}
          />
          <Button
            type="primary"
            loading={sharePending}
            disabled={!canManageShare}
            onClick={() => void createShare()}
          >
            创建只读链接
          </Button>
        </Space>
        {shareUrl ? (
          <Alert
            className="share-created-alert"
            type="success"
            showIcon
            title="链接已创建，请立即复制保存"
            description={<Input value={shareUrl} readOnly />}
          />
        ) : null}
        <div className="share-link-list">
          {shareLinks.length ? (
            shareLinks.map((link) => (
              <Card
                key={link.id}
                size="small"
                title={
                  <Space>
                    <Tag color={shareStatusColor(link.status)}>{shareStatusLabel(link.status)}</Tag>
                    <Typography.Text type="secondary">
                      创建于 {new Date(link.createdAt).toLocaleString()}
                    </Typography.Text>
                  </Space>
                }
                extra={
                  link.status === "ACTIVE" ? (
                    <Button
                      danger
                      size="small"
                      disabled={!canManageShare || sharePending}
                      onClick={() => void revokeShare(link.id)}
                    >
                      撤销
                    </Button>
                  ) : null
                }
              >
                <Typography.Text type="secondary">
                  {link.expiresAt
                    ? `有效期至 ${new Date(link.expiresAt).toLocaleString()}`
                    : "永不过期"}
                </Typography.Text>
              </Card>
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未创建分享链接" />
          )}
        </div>
      </Modal>

      <Modal
        title="自动排表"
        open={generationOpen}
        onCancel={() => {
          setGenerationOpen(false);
          setGenerationFailure(null);
        }}
        onOk={() => void generate()}
        okText="开始生成"
        confirmLoading={generationPending}
        okButtonProps={{ disabled: !canGenerateSchedule }}
      >
        <Typography.Paragraph type="secondary">
          求解器会优先安排更多角色、填满前面波次并优化队伍组成、核心秘宝、跨波平衡和强度顺序。
        </Typography.Paragraph>
        {validation ? (
          <Alert
            type={validation.summary.warning ? "warning" : "success"}
            showIcon
            title={validation.summary.warning ? `预检查通过，仍有 ${validation.summary.warning} 个提醒` : "预检查通过"}
            description="生成将使用当前参团名单、玩家偏好、锁定和已确认规则。"
          />
        ) : null}
        {generationFailure ? (
          <Alert
            type="error"
            showIcon
            title={
              generationFailure.code === "SCHEDULE_GENERATION_TIMEOUT"
                ? "本次求解达到时限"
                : generationFailure.code === "SCHEDULE_GENERATION_INFEASIBLE"
                  ? "当前硬性条件确实无解"
                  : "求解器执行异常"
            }
            description={
              generationFailure.code === "SCHEDULE_GENERATION_TIMEOUT"
                ? `${generationFailure.message}。下方高级参数已更新为建议值，可直接再次生成。`
                : generationFailure.message
            }
          />
        ) : null}
        <Space orientation="vertical" className="full-width" size="middle">
          <Space>
            <Switch
              checked={generationPreserveLocks}
              onChange={setGenerationPreserveLocks}
            />
            保留当前锁定安排，仅重新生成未锁定部分
          </Space>
          <details className="generation-advanced">
            <summary>高级设置</summary>
          <Row gutter={12} className="full-width generation-advanced-fields">
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
              <Typography.Text type="secondary">方案种子</Typography.Text>
              <Space.Compact className="full-width">
                <InputNumber
                  min={0}
                  max={2_147_483_647}
                  className="full-width"
                  value={generationSeed}
                  onChange={(value) => setGenerationSeed(value ?? 42)}
                />
                <Button
                  aria-label="更换方案种子"
                  icon={<ReloadOutlined />}
                  onClick={() =>
                    setGenerationSeed((seed) => (seed >= 2_147_483_647 ? 1 : seed + 1))
                  }
                />
              </Space.Compact>
            </Col>
          </Row>
          <Typography.Text type="secondary">
            相同数据、规则、锁定和种子可复现同一方案；更换种子可探索同等硬约束下的其他可行编队。
          </Typography.Text>
          </details>
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
        okButtonProps={{
          disabled: !canCreateContent || !copyName.trim() || !copyTargetVersionId,
        }}
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
        okButtonProps={{ disabled: !canEditSchedule || !syncPreview?.changes.length }}
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
        okButtonProps={{ disabled: !canEditSchedule }}
      >
        <Typography.Paragraph type="secondary">
          可用波次留空表示全程可用；最大出场次数为空表示不额外限制。
        </Typography.Paragraph>
        <div className="preference-batch-toolbar">
          <Checkbox
            checked={preferencesSelectedOnly}
            onChange={(event) => setPreferencesSelectedOnly(event.target.checked)}
          >
            仅显示已选角色的玩家
          </Checkbox>
          <Space wrap size={4}>
            <Button
              size="small"
              onClick={() =>
                setPreferenceDrafts((current) =>
                  current.map((item) =>
                    !preferencesSelectedOnly || selectedPlayerIds.has(item.playerId)
                      ? { ...item, allowedWaves: null }
                      : item,
                  ),
                )
              }
            >
              批量全程可用
            </Button>
            <Button
              size="small"
              onClick={() =>
                setPreferenceDrafts((current) =>
                  current.map((item) =>
                    !preferencesSelectedOnly || selectedPlayerIds.has(item.playerId)
                      ? { ...item, preferEarly: false, preferContiguous: false, maxWaveCount: null }
                      : item,
                  ),
                )
              }
            >
              清空软偏好
            </Button>
          </Space>
        </div>
        <div className="preference-list">
          {preferenceDrafts
            .filter((preference) => !preferencesSelectedOnly || selectedPlayerIds.has(preference.playerId))
            .map((preference) => {
            const player = detail.participants.find(
              (participant) => participant.playerIdSnapshot === preference.playerId,
            );
            return (
              <div className="preference-row" key={preference.playerId}>
                <Typography.Text strong className="preference-player">
                  {player?.playerNameSnapshot ?? preference.playerId}
                </Typography.Text>
                <div className="preference-availability">
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
                </div>
                <div>
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
                </div>
                <div className="preference-switches">
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
                </div>
              </div>
            );
          })}
        </div>
      </Modal>

      <Modal
        title="排表信息"
        open={metadataOpen}
        onCancel={() => setMetadataOpen(false)}
        onOk={() => void saveMetadata()}
        okText="保存"
        okButtonProps={{ disabled: !canEditSchedule || !metadataName.trim() }}
      >
        <Form layout="vertical" className="schedule-metadata-form">
          <Form.Item label="排表名称" required>
            <Input
              value={metadataName}
              maxLength={160}
              onChange={(event) => setMetadataName(event.target.value)}
            />
          </Form.Item>
          <Form.Item label="备注">
            <Input.TextArea
              value={metadataNote}
              maxLength={1000}
              showCount
              rows={3}
              onChange={(event) => setMetadataNote(event.target.value)}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="自动排表生成记录"
        open={generationHistoryOpen}
        onCancel={() => setGenerationHistoryOpen(false)}
        footer={<Button onClick={() => setGenerationHistoryOpen(false)}>关闭</Button>}
        width={760}
      >
        <Typography.Paragraph type="secondary">
          记录由服务端持久化。最上方两次结果会用于质量对比，人工调整不会删除历史结果。
        </Typography.Paragraph>
        <div className="generation-history-list">
          {generationRuns.length ? generationRuns.map((run, index) => (
            <Card
              key={run.id}
              size="small"
              title={`第 ${generationRuns.length - index} 次 · 种子 ${run.randomSeed}`}
              extra={run.resultRevision === detail.revision ? <Tag color="green">当前修订</Tag> : <Tag>历史修订 {run.resultRevision ?? "-"}</Tag>}
            >
              <Space wrap size={[4, 4]}>
                <Tag color={run.status === "SUCCEEDED" ? "green" : "orange"}>{GENERATION_STATUS_LABELS[run.status]}</Tag>
                <Tag>耗时 {run.durationMs ?? 0} ms</Tag>
                {run.objectiveSummary ? (
                  <>
                    <Tag color="blue">已安排 {run.objectiveSummary.assignedCount}/{run.objectiveSummary.participantCount}</Tag>
                    <Tag>完整波次 {run.objectiveSummary.completeWaveCount}</Tag>
                    <Tag>完整队伍 {run.objectiveSummary.completeTeamCount}</Tag>
                    <Tag>强度冲突 {run.objectiveSummary.strengthOrderViolationCount}</Tag>
                  </>
                ) : null}
              </Space>
            </Card>
          )) : <Empty description="尚无生成记录" />}
        </div>
      </Modal>

      <Modal
        title="永久删除排表"
        open={deleteOpen}
        confirmLoading={lifecyclePending}
        okText="确认永久删除"
        okButtonProps={{
          danger: true,
          disabled: deleteConfirmation !== detail.name,
        }}
        onCancel={() => setDeleteOpen(false)}
        onOk={() => void permanentlyDeleteSchedule()}
      >
        <Alert
          type="error"
          showIcon
          title="此操作无法恢复"
          description="仅从未发布的草稿允许永久删除，相关编队、规则和生成记录也会一并删除。"
        />
        <Typography.Paragraph className="schedule-delete-confirmation">
          请输入排表名称 <Typography.Text code>{detail.name}</Typography.Text> 以确认：
        </Typography.Paragraph>
        <Input
          value={deleteConfirmation}
          placeholder={detail.name}
          onChange={(event) => setDeleteConfirmation(event.target.value)}
          onPressEnter={() => {
            if (deleteConfirmation === detail.name) void permanentlyDeleteSchedule();
          }}
        />
      </Modal>
    </section>
  );
}

function ScheduleSnapshotPreview({ schedule }: { schedule: ScheduleDetail }) {
  const participantById = new Map(
    schedule.participants.map((participant) => [participant.id, participant]),
  );
  return (
    <div className="snapshot-preview">
      <Typography.Title level={4}>{schedule.name}</Typography.Title>
      <Typography.Text type="secondary">
        {schedule.waveCount} 波 · 修订 {schedule.revision}
      </Typography.Text>
      <div className="wave-list snapshot-preview-waves">
        {schedule.waves.map((wave) => (
          <Card
            key={wave.id}
            size="small"
            title={`第 ${wave.waveNo} 波`}
            extra={`C ${wave.damageTotal} 亿 · 奶 ${wave.bufferTotal}`}
          >
            <Row gutter={[8, 8]}>
              {wave.teams.map((team) => (
                <Col
                  xs={24}
                  xl={Math.max(6, Math.floor(24 / wave.teams.length))}
                  key={team.id}
                >
                  <Card
                    size="small"
                    className="team-card"
                    style={{ borderTopColor: team.displayColorSnapshot }}
                    title={`${team.displayNameSnapshot} · ${team.compositionCode}`}
                  >
                    {team.slots.map((slot) => {
                      const participant = slot.participantId
                        ? participantById.get(slot.participantId)
                        : undefined;
                      return (
                        <div className="team-slot" key={slot.id}>
                          {participant ? (
                            <ScheduleParticipantLabel
                              participant={participant}
                              compact
                              core={wave.specialAssignments.some(
                                (assignment) => assignment.participantId === participant.id,
                              )}
                            />
                          ) : (
                            <Typography.Text type="secondary">待补</Typography.Text>
                          )}
                        </div>
                      );
                    })}
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        ))}
      </div>
    </div>
  );
}

function shareStatusColor(status: ShareLinkView["status"]): string {
  return status === "ACTIVE" ? "green" : status === "EXPIRED" ? "orange" : "default";
}

function shareStatusLabel(status: ShareLinkView["status"]): string {
  return status === "ACTIVE" ? "有效" : status === "EXPIRED" ? "已过期" : "已撤销";
}

function GenerationSummary({
  run,
  previousRun,
  participants,
  currentRevision,
  runCount,
  canTryAlternative,
  onOpenHistory,
  onTryAlternative,
}: {
  run: GenerationRun;
  previousRun: GenerationRun | null;
  participants: ScheduleParticipant[];
  currentRevision: number;
  runCount: number;
  canTryAlternative: boolean;
  onOpenHistory: () => void;
  onTryAlternative: () => void;
}) {
  const summary = run.objectiveSummary;
  const participantById = new Map(participants.map((participant) => [participant.id, participant]));
  const unassigned = run.diagnostics?.unassigned ?? [];
  const issues = run.diagnostics?.issues ?? [];
  const objectiveStages = run.diagnostics?.objectiveStages ?? [];
  const comparison = compareGenerationRuns(run, previousRun);
  return (
    <Card
      title="最近一次自动排表"
      className="schedule-panel generation-summary-card"
      size="small"
      extra={
        <Space size={4}>
          <Button type="text" size="small" icon={<HistoryOutlined />} onClick={onOpenHistory}>
            生成记录 {runCount}
          </Button>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            disabled={!canTryAlternative}
            onClick={onTryAlternative}
          >
            换一个方案
          </Button>
        </Space>
      }
    >
      <Space wrap className="generation-summary-tags">
        <Tag color={run.status === "SUCCEEDED" ? "green" : "orange"}>
          {GENERATION_STATUS_LABELS[run.status]}
        </Tag>
        {run.resultRevision === currentRevision ? (
          <Tag color="green">对应当前修订</Tag>
        ) : (
          <Tag color="default">生成后已人工调整</Tag>
        )}
        <Tag>耗时 {run.durationMs ?? 0} ms</Tag>
        <Tag>种子 {run.randomSeed}</Tag>
        {summary ? (
          <>
            <Tag color="blue">
              已安排 {summary.assignedCount}/{summary.participantCount}
            </Tag>
            <Tag color="cyan">完整波次 {summary.completeWaveCount}</Tag>
            <Tag color="purple">完整队伍 {summary.completeTeamCount}</Tag>
            <Tag color="geekblue">优先组成 {summary.preferredCompositionCount}</Tag>
            <Tag color="gold">核心满足 {summary.specialRuleSatisfiedCount}</Tag>
            {summary.damageSpreadDisplay !== undefined ? (
              <Tag>C 跨波差 {summary.damageSpreadDisplay} 亿</Tag>
            ) : null}
            {summary.bufferSpreadDisplay !== undefined ? (
              <Tag>奶跨波差 {summary.bufferSpreadDisplay}</Tag>
            ) : null}
            <Tag color={summary.strengthOrderViolationCount ? "orange" : "green"}>
              强度顺序冲突 {summary.strengthOrderViolationCount}
            </Tag>
          </>
        ) : null}
      </Space>
      {comparison ? (
        <Alert
          className="generation-comparison"
          type={comparison.improved ? "success" : comparison.declined ? "warning" : "info"}
          showIcon
          title={comparison.title}
          description={comparison.description}
        />
      ) : null}
      {objectiveStages.length ? (
        <div className="generation-objective-stages">
          <Typography.Text strong>优化阶段</Typography.Text>
          <Space wrap size={[4, 4]}>
            {objectiveStages.map((stage) => (
              <Tag
                key={stage.code}
                color={
                  stage.outcome === "FEASIBLE"
                    ? "orange"
                    : stage.outcome === "TARGET_REACHED"
                      ? "blue"
                      : "green"
                }
                title={`目标值 ${stage.value} · 用时 ${stage.durationMs} ms`}
              >
                {OBJECTIVE_STAGE_LABELS[stage.code] ?? stage.code} · {OBJECTIVE_OUTCOME_LABELS[stage.outcome]}
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
      {run.ruleEvaluation?.length ? (
        <div className="generation-objective-stages">
          <Typography.Text strong>本次排表要求</Typography.Text>
          <Space wrap size={[4, 4]}>
            {run.ruleEvaluation.map((evaluation) => (
              <Tag
                key={evaluation.ruleId}
                color={RULE_EVALUATION_LABELS[evaluation.status].color}
                title={evaluation.reason}
              >
                {RULE_TYPE_LABELS[evaluation.type] ?? evaluation.type} ·{
                  RULE_EVALUATION_LABELS[evaluation.status].label
                } · {evaluation.explanation}
                {evaluation.reason ? ` · ${evaluation.reason}` : ""}
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
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

export function compareGenerationRuns(
  current: GenerationRun,
  previous: GenerationRun | null,
): { improved: boolean; declined: boolean; title: string; description: string } | null {
  const currentSummary = current.objectiveSummary;
  const previousSummary = previous?.objectiveSummary;
  if (!currentSummary || !previousSummary) return null;
  const metrics = [
    {
      label: "已安排",
      current: currentSummary.assignedCount,
      previous: previousSummary.assignedCount,
      lowerIsBetter: false,
    },
    {
      label: "完整波次",
      current: currentSummary.completeWaveCount,
      previous: previousSummary.completeWaveCount,
      lowerIsBetter: false,
    },
    {
      label: "完整队伍",
      current: currentSummary.completeTeamCount,
      previous: previousSummary.completeTeamCount,
      lowerIsBetter: false,
    },
    {
      label: "优先组成",
      current: currentSummary.preferredCompositionCount,
      previous: previousSummary.preferredCompositionCount,
      lowerIsBetter: false,
    },
    {
      label: "核心满足",
      current: currentSummary.specialRuleSatisfiedCount,
      previous: previousSummary.specialRuleSatisfiedCount,
      lowerIsBetter: false,
    },
    {
      label: "强度顺序冲突",
      current: currentSummary.strengthOrderViolationCount,
      previous: previousSummary.strengthOrderViolationCount,
      lowerIsBetter: true,
    },
    {
      label: "C 跨波差",
      current: currentSummary.damageSpread,
      previous: previousSummary.damageSpread,
      lowerIsBetter: true,
    },
    {
      label: "奶跨波差",
      current: currentSummary.bufferSpread,
      previous: previousSummary.bufferSpread,
      lowerIsBetter: true,
    },
  ];
  const firstDifference = metrics.find((metric) => metric.current !== metric.previous);
  const changed = metrics
    .filter((metric) => metric.current !== metric.previous)
    .map((metric) => `${metric.label} ${metric.previous} → ${metric.current}`);
  if (!firstDifference) {
    return {
      improved: false,
      declined: false,
      title: `与种子 ${previous.randomSeed} 的关键质量指标相同`,
      description: "角色位置可能不同；硬约束和主要质量指标没有变化。",
    };
  }
  const improved = firstDifference.lowerIsBetter
    ? firstDifference.current < firstDifference.previous
    : firstDifference.current > firstDifference.previous;
  return {
    improved,
    declined: !improved,
    title: improved
      ? `关键指标优于种子 ${previous.randomSeed}`
      : `关键指标不优于种子 ${previous.randomSeed}`,
    description: changed.join("；"),
  };
}

function allScheduleSlots(schedule: ScheduleDetail): ScheduleSlot[] {
  return schedule.waves.flatMap((wave) => wave.teams.flatMap((team) => team.slots));
}

export function buildDropOperations(
  schedule: ScheduleDetail,
  participantId: string,
  targetSlotId: string,
): ScheduleOperation[] {
  const slots = allScheduleSlots(schedule);
  const target = slots.find((slot) => slot.id === targetSlotId);
  if (!target || target.participantId === participantId) return [];
  if (!target.participantId) {
    return [{ type: "MOVE_PARTICIPANT", participantId, toSlotId: targetSlotId }];
  }
  const source = slots.find((slot) => slot.participantId === participantId);
  if (source) {
    return [
      {
        type: "SWAP_PARTICIPANTS",
        participantId,
        otherParticipantId: target.participantId,
      },
    ];
  }
  return [
    { type: "UNASSIGN_PARTICIPANT", participantId: target.participantId },
    { type: "MOVE_PARTICIPANT", participantId, toSlotId: targetSlotId },
  ];
}

export function applyOptimisticAssignment(
  schedule: ScheduleDetail,
  operations: ScheduleOperation[],
): ScheduleDetail {
  const next: ScheduleDetail = {
    ...schedule,
    participants: schedule.participants.map((participant) => ({ ...participant })),
    waves: schedule.waves.map((wave) => ({
      ...wave,
      specialAssignments: wave.specialAssignments.map((assignment) => ({ ...assignment })),
      teams: wave.teams.map((team) => ({
        ...team,
        slots: team.slots.map((slot) => ({ ...slot })),
      })),
    })),
  };
  const participantById = new Map(next.participants.map((item) => [item.id, item]));
  const slots = allScheduleSlots(next);

  for (const operation of operations) {
    if (operation.type === "UNASSIGN_PARTICIPANT" && operation.participantId) {
      const source = slots.find((slot) => slot.participantId === operation.participantId);
      if (source) source.participantId = null;
      const participant = participantById.get(operation.participantId);
      if (participant) participant.unassignedReason = { code: "MANUALLY_UNASSIGNED" };
    }
    if (
      operation.type === "MOVE_PARTICIPANT" &&
      operation.participantId &&
      operation.toSlotId
    ) {
      const source = slots.find((slot) => slot.participantId === operation.participantId);
      const target = slots.find((slot) => slot.id === operation.toSlotId);
      if (source) source.participantId = null;
      if (target) target.participantId = operation.participantId;
      const participant = participantById.get(operation.participantId);
      if (participant) participant.unassignedReason = null;
    }
    if (
      operation.type === "SWAP_PARTICIPANTS" &&
      operation.participantId &&
      operation.otherParticipantId
    ) {
      const source = slots.find((slot) => slot.participantId === operation.participantId);
      const target = slots.find((slot) => slot.participantId === operation.otherParticipantId);
      if (source && target) {
        [source.participantId, target.participantId] = [target.participantId, source.participantId];
      }
    }
  }

  for (const wave of next.waves) {
    for (const team of wave.teams) {
      const members = team.slots
        .map((slot) => participantById.get(slot.participantId ?? ""))
        .filter((participant): participant is ScheduleParticipant => Boolean(participant));
      team.damageTotal = String(
        members.reduce((total, item) => total + Number(item.damageScoreSnapshot ?? 0), 0),
      );
      team.bufferTotal = String(
        members.reduce((total, item) => total + Number(item.bufferScoreSnapshot ?? 0), 0),
      );
    }
    wave.damageTotal = String(
      wave.teams.reduce((total, team) => total + Number(team.damageTotal), 0),
    );
    wave.bufferTotal = String(
      wave.teams.reduce((total, team) => total + Number(team.bufferTotal), 0),
    );
    wave.specialAssignments = wave.specialAssignments.filter((assignment) =>
      wave.teams.some(
        (team) =>
          team.teamKey === assignment.targetTeamKeySnapshot &&
          team.slots.some((slot) => slot.participantId === assignment.participantId),
      ),
    );
  }
  return next;
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

export function describeIssue(issue: ValidationIssue): string {
  const params = issue.message_params;
  switch (issue.code) {
    case "TEAM_INCOMPLETE":
      return `第 ${params.waveNo} 波 ${params.teamKey} 队存在待补位置。`;
    case "TEAM_COMPOSITION_INVALID":
      return `第 ${params.waveNo} 波 ${params.teamKey} 队的角色组成不符合副本规则。`;
    case "PLAYER_DUPLICATE_IN_WAVE":
      return `第 ${params.waveNo} 波同一玩家安排了 ${params.count} 个角色。`;
    case "PARTICIPANT_WAVE_NOT_ALLOWED":
      return `第 ${params.waveNo} 波安排了玩家不可用的角色。`;
    case "PLAYER_MAX_WAVE_COUNT_EXCEEDED":
      return `玩家最多参加 ${params.maximum} 波，当前已安排 ${params.current} 波。`;
    case "MISSING_WAVE_CORE":
      return `第 ${params.waveNo} 波缺少规则 ${params.ruleCode} 要求的核心角色。`;
    case "DAMAGE_ORDER_VIOLATION":
    case "BUFFER_ORDER_VIOLATION":
      return `第 ${params.waveNo} 波 ${params.strongerTeamKey} 队弱于 ${params.weakerTeamKey} 队。`;
    case "UNASSIGNED_SELECTED_PARTICIPANTS":
      return `仍有 ${params.count} 个已选角色未分配到位置。`;
    case "CAPACITY_EXCEEDED":
      return `容量 ${params.capacity}，当前 ${params.current}，请减少角色或增加波数。`;
    case "PARTICIPANT_SHORTAGE":
      return `容量 ${params.capacity}，当前 ${params.current}，还缺 ${params.shortage} 个角色。`;
    case "DISTINCT_PLAYER_SHORTAGE":
      return `每波需要 ${params.required} 个不同玩家，当前只有 ${params.current} 个，还缺 ${params.shortage} 个；同一玩家在同一波最多使用一个角色。`;
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

export function describeRuleResolutionIssue(issue: RuleResolutionIssue): string {
  const reference = issue.reference ? `“${issue.reference}”` : "该要求";
  switch (issue.code) {
    case "RULE_SET_TYPE_UNSUPPORTED":
      return `${reference}暂时无法转换为系统支持的排表规则，请改用明确的玩家、角色、波次或队伍要求。`;
    case "RULE_SET_CANDIDATE_DUPLICATED":
      return `解析结果中规则 ${issue.candidateId ?? ""} 重复，请重新解析。`;
    case "RULE_SET_REFERENCE_NOT_FOUND":
      return `在当前参团角色和副本队伍中未找到${reference}，请检查名称或先同步人员。`;
    case "RULE_SET_REFERENCE_AMBIGUOUS":
      return `${reference}对应多个候选${issue.matches.length ? `：${issue.matches.join("、")}` : ""}，请补充玩家或职业信息。`;
    case "RULE_SET_WAVE_OUT_OF_RANGE":
      return `${reference}不在当前排表的波次范围内，请修改波次后重新解析。`;
    case "RULE_SET_HARD_CONFLICT":
      return `${reference}${issue.matches.length ? `；关联规则：${issue.matches.join("、")}` : ""}。请调整冲突要求后重新解析。`;
    default:
      return issue.reference
        ? `无法确认${reference}${issue.matches.length ? `；候选：${issue.matches.join("、")}` : ""}`
        : "该要求当前无法确认，请修改描述后重新解析。";
  }
}

export function describeRuleParseError(error: unknown): unknown {
  if (!(error instanceof ApiError)) return error;
  if (error.code === "RULE_PARSE_RATE_LIMITED") {
    const retryAfter = Number(error.details.retryAfterSeconds);
    return new Error(
      Number.isFinite(retryAfter)
        ? `规则解析请求过于频繁，请在 ${Math.max(1, Math.ceil(retryAfter))} 秒后重试`
        : "规则解析请求过于频繁，请稍后重试",
    );
  }
  if (error.code === "RULE_PROVIDER_UNAVAILABLE") {
    return new Error("自然语言服务暂时不可用，请稍后重试；手动排表和已确认规则不受影响");
  }
  if (error.code === "RULE_PROVIDER_RESPONSE_INVALID") {
    return new Error("模型返回的规则格式无法识别，请调整描述后重新解析");
  }
  return error;
}
