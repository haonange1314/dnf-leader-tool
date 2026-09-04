import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  HistoryOutlined,
  HolderOutlined,
  MoreOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
  type MenuProps,
} from "antd";
import { useEffect, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  type Character,
  type ImportBatch,
  type ImportBatchList,
  type ImportBatchSummary,
  type ImportChange,
  type ImportRow,
  type Player,
  type User,
} from "../../api/client";

interface Props {
  userRole: User["role"];
  permissions?: string[];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

export function PersonnelPage({ userRole, permissions, onError, onSuccess }: Props) {
  const canEdit = permissions ? permissions.includes("ROSTER_WRITE") : userRole !== "VIEWER";
  const canImport = permissions ? permissions.includes("ROSTER_IMPORT") : userRole !== "VIEWER";
  const [players, setPlayers] = useState<Player[]>([]);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [editingPlayer, setEditingPlayer] = useState<Player | null>(null);
  const [characterPlayer, setCharacterPlayer] = useState<Player | null>(null);
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<ImportBatchSummary[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyDetail, setHistoryDetail] = useState<ImportBatch | null>(null);
  const [sortPending, setSortPending] = useState(false);
  const [playerForm] = Form.useForm();
  const [characterForm] = Form.useForm();
  const characterRole = Form.useWatch("roleType", characterForm);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const load = async () => {
    try {
      setPlayers(
        (await api<{ items: Player[] }>("/players")).items,
      );
    } catch (error) {
      onError(error);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const openCreatePlayer = () => {
    setEditingPlayer(null);
    playerForm.resetFields();
    setPlayerOpen(true);
  };
  const openEditPlayer = (player: Player) => {
    setEditingPlayer(player);
    playerForm.setFieldsValue({
      displayName: player.displayName,
      isActive: player.isActive,
    });
    setPlayerOpen(true);
  };
  const closePlayer = () => {
    setPlayerOpen(false);
    setEditingPlayer(null);
    playerForm.resetFields();
  };
  const savePlayer = async (values: Record<string, unknown>) => {
    try {
      await api(editingPlayer ? `/players/${editingPlayer.id}` : "/players", {
        method: editingPlayer ? "PATCH" : "POST",
        body: JSON.stringify(
          editingPlayer ? values : { ...values, characters: [] },
        ),
      });
      closePlayer();
      onSuccess(editingPlayer ? "玩家信息已修改" : "玩家已添加");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const deletePlayer = (player: Player) => {
    Modal.confirm({
      title: `永久删除玩家“${player.displayName}”？`,
      content: `将同时永久删除该玩家的 ${player.characters.length} 个角色，且无法恢复。若已有排表引用，系统会拒绝删除。`,
      okText: "永久删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api(`/players/${player.id}`, { method: "DELETE" });
          onSuccess("玩家及其角色已永久删除");
          await load();
        } catch (error) {
          onError(error);
        }
      },
    });
  };
  const openCreateCharacter = (player: Player) => {
    setEditingCharacter(null);
    characterForm.resetFields();
    setCharacterPlayer(player);
  };
  const openEditCharacter = (player: Player, character: Character) => {
    setEditingCharacter(character);
    characterForm.setFieldsValue({
      profession: character.profession,
      roleType: character.roleType,
      score: character.damageScore ?? character.bufferScore,
      isTreasureDamage: character.isTreasureDamage,
      isFixedLeadTeamBuffer: character.isFixedLeadTeamBuffer,
      isGroupHunt: character.isGroupHunt,
      defaultRaidParticipant: character.defaultRaidParticipant,
      isActive: character.isActive,
    });
    setCharacterPlayer(player);
  };
  const closeCharacter = () => {
    setCharacterPlayer(null);
    setEditingCharacter(null);
    characterForm.resetFields();
  };
  const saveCharacter = async (values: Record<string, unknown>) => {
    if (!characterPlayer) return;
    const { score, ...rest } = values;
    const role = values.roleType;
    const normalizedScore =
      role === "DAMAGE" && Number.isFinite(Number(score))
        ? Math.round(Number(score))
        : score;
    const payload = {
      ...rest,
      damageScore: role === "DAMAGE" ? normalizedScore : null,
      bufferScore: role === "BUFFER" ? normalizedScore : null,
      isTreasureDamage: role === "DAMAGE" && values.isTreasureDamage,
      isFixedLeadTeamBuffer:
        role === "BUFFER" && values.isFixedLeadTeamBuffer,
      isGroupHunt: role === "DAMAGE" && values.isGroupHunt,
      note: editingCharacter?.note ?? null,
    };
    try {
      await api(
        editingCharacter
          ? `/characters/${editingCharacter.id}`
          : `/players/${characterPlayer.id}/characters`,
        {
          method: editingCharacter ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      );
      closeCharacter();
      onSuccess(editingCharacter ? "角色信息已修改" : "角色已添加");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const deleteCharacter = (character: Character) => {
    Modal.confirm({
      title: `永久删除角色“${character.profession}”？`,
      content: "删除后无法恢复。若已有排表引用，系统会拒绝删除。",
      okText: "永久删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api(`/characters/${character.id}`, { method: "DELETE" });
          onSuccess("角色已永久删除");
          await load();
        } catch (error) {
          onError(error);
        }
      },
    });
  };
  const preview = async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    setBatch(null);
    setImportError(null);
    try {
      const result = await api<ImportBatch>("/imports/characters/preview", {
        method: "POST",
        body,
      });
      setBatch(result);
      onSuccess("全量同步预览已生成");
    } catch (error) {
      setImportError(
        error instanceof ApiError ? error.message : "无法生成导入预览，请检查文件后重试",
      );
      onError(error);
    }
    return false;
  };
  const commit = async () => {
    if (!batch) return;
    try {
      await api<ImportBatch>(
        `/imports/characters/${batch.id}/commit`,
        { method: "POST" },
      );
      setBatch(null);
      setImportError(null);
      onSuccess("人员数据已同步");
      await load();
    } catch (error) {
      setImportError(
        error instanceof ApiError ? error.message : "人员同步失败，请重新预览后重试",
      );
      onError(error);
    }
  };
  const confirmCommit = () => {
    if (!batch) return;
    Modal.confirm({
      title: "确认按 Excel 全量同步人员？",
      content: (
        <Typography.Text>
          文件外的 {batch.summary.deactivate_players} 名玩家、
          {batch.summary.deactivate} 个角色将被停用，不再进入新排表；历史排表不受影响。
        </Typography.Text>
      ),
      okText: "确认同步",
      cancelText: "取消",
      okButtonProps: {
        danger:
          batch.summary.deactivate_players > 0 || batch.summary.deactivate > 0,
      },
      onOk: commit,
    });
  };
  const loadHistory = async (page = 1) => {
    setHistoryLoading(true);
    try {
      const result = await api<ImportBatchList>(
        `/imports/characters/history?limit=10&offset=${(page - 1) * 10}`,
      );
      setHistory(result.items);
      setHistoryTotal(result.total);
      setHistoryPage(page);
    } catch (error) {
      onError(error);
    } finally {
      setHistoryLoading(false);
    }
  };
  const openHistory = () => {
    setHistoryOpen(true);
    setHistoryDetail(null);
    void loadHistory(1);
  };
  const openHistoryDetail = async (batchId: string) => {
    setHistoryLoading(true);
    try {
      setHistoryDetail(await api<ImportBatch>(`/imports/characters/${batchId}`));
    } catch (error) {
      onError(error);
    } finally {
      setHistoryLoading(false);
    }
  };
  const reorderPlayers = async ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id || sortPending) return;
    const oldIndex = players.findIndex((player) => player.id === active.id);
    const newIndex = players.findIndex((player) => player.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const previous = players;
    const reordered = arrayMove(players, oldIndex, newIndex);
    setPlayers(reordered);
    setSortPending(true);
    try {
      await api("/players/reorder", {
        method: "PUT",
        body: JSON.stringify({ orderedIds: reordered.map((player) => player.id) }),
      });
      onSuccess("玩家顺序已保存");
    } catch (error) {
      setPlayers(previous);
      onError(error);
      await load();
    } finally {
      setSortPending(false);
    }
  };
  const reorderCharacters = async (playerId: string, { active, over }: DragEndEvent) => {
    if (!over || active.id === over.id || sortPending) return;
    const player = players.find((item) => item.id === playerId);
    if (!player) return;
    const oldIndex = player.characters.findIndex((character) => character.id === active.id);
    const newIndex = player.characters.findIndex((character) => character.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const previous = players;
    const reorderedCharacters = arrayMove(player.characters, oldIndex, newIndex);
    setPlayers((current) =>
      current.map((item) =>
        item.id === playerId ? { ...item, characters: reorderedCharacters } : item,
      ),
    );
    setSortPending(true);
    try {
      await api(`/players/${playerId}/characters/reorder`, {
        method: "PUT",
        body: JSON.stringify({
          orderedIds: reorderedCharacters.map((character) => character.id),
        }),
      });
      onSuccess("角色顺序已保存");
    } catch (error) {
      setPlayers(previous);
      onError(error);
      await load();
    } finally {
      setSortPending(false);
    }
  };
  return (
    <section>
      <div className="section-heading">
        <div>
          <Typography.Title level={2}>人员管理</Typography.Title>
          <Typography.Text type="secondary">
            以玩家分组维护 C、奶与默认参团属性
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={!canEdit}
          onClick={openCreatePlayer}
        >
          新增玩家
        </Button>
      </div>
      <Card className="import-strip">
        <Space wrap>
          <Button
            icon={<DownloadOutlined />}
            href="/api/v1/imports/characters/template"
          >
            下载 Excel 模板
          </Button>
          <Button
            icon={<DownloadOutlined />}
            href="/api/v1/imports/characters/export.xlsx"
          >
            导出当前人员
          </Button>
          <Upload
            disabled={!canImport}
            accept=".xlsx"
            showUploadList={false}
            beforeUpload={preview}
          >
            <Button disabled={!canImport} icon={<UploadOutlined />}>
              上传并预览
            </Button>
          </Upload>
          <Button
            disabled={!canImport}
            icon={<HistoryOutlined />}
            onClick={openHistory}
          >
            导入记录
          </Button>
          {batch && (
            <>
              <Tag color={batch.summary.error ? "red" : "blue"}>
                新增 {batch.summary.create} · 更新 {batch.summary.update} · 恢复玩家{" "}
                {batch.summary.reactivate_players} · 忽略 {batch.summary.ignore} ·
                将停用玩家 {batch.summary.deactivate_players} · 将停用角色{" "}
                {batch.summary.deactivate} · 调整顺序 {batch.summary.reorder ?? 0} · 错误{" "}
                {batch.summary.error}
              </Tag>
              <Button
                type="primary"
                disabled={
                  !canImport || batch.summary.error > 0 || batch.status !== "PREVIEWED"
                }
                onClick={confirmCommit}
              >
                确认同步
              </Button>
              {batch.summary.error > 0 && (
                <Button href={`/api/v1/imports/characters/${batch.id}/errors.xlsx`}>
                  下载错误
                </Button>
              )}
            </>
          )}
        </Space>
        {importError && (
          <Alert
            className="personnel-import-error"
            type="error"
            showIcon
            message="导入失败"
            description={importError}
          />
        )}
        {batch && batch.summary.error > 0 && (
          <Table<ImportRow>
            className="personnel-import-errors"
            size="small"
            rowKey="row_no"
            dataSource={batch.rows.filter((row) => row.errors.length > 0)}
            pagination={{ pageSize: 5, hideOnSinglePage: true, size: "small" }}
            columns={[
              { title: "Excel 行", dataIndex: "row_no", width: 88 },
              {
                title: "玩家",
                render: (_, row) => row.payload.player_name || "—",
              },
              {
                title: "职业",
                render: (_, row) => row.payload.profession || "—",
              },
              {
                title: "错误原因",
                render: (_, row) => row.errors.map((item) => item.message).join("；"),
              },
            ]}
          />
        )}
        {batch && batch.summary.error === 0 && (batch.change_details ?? []).length > 0 && (
          <ImportChangeTable changes={batch.change_details ?? []} />
        )}
        {batch && batch.summary.error === 0 && (batch.change_details ?? []).length === 0 && (
          <Alert
            className="personnel-import-error"
            type="success"
            showIcon
            message="文件与当前人员数据一致，没有需要写入的变更"
          />
        )}
      </Card>
      <Typography.Text type="secondary" className="personnel-sort-hint">
        拖动手柄调整玩家顺序；展开玩家后可拖动角色卡片排序
      </Typography.Text>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={(event) => void reorderPlayers(event)}
      >
        <SortableContext
          items={players.map((player) => player.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="personnel-list">
            {players.map((player) => (
              <SortablePlayerPanel
                key={player.id}
                player={player}
                dragDisabled={!canEdit || sortPending}
                canEdit={canEdit}
                onAddCharacter={openCreateCharacter}
                onEditPlayer={openEditPlayer}
                onDeletePlayer={deletePlayer}
                onEditCharacter={openEditCharacter}
                onDeleteCharacter={deleteCharacter}
                onCharacterDragEnd={reorderCharacters}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      <Modal
        title={editingPlayer ? "修改玩家" : "新增玩家"}
        open={playerOpen}
        onCancel={closePlayer}
        onOk={() => playerForm.submit()}
      >
        <Form
          form={playerForm}
          layout="vertical"
          initialValues={{ isActive: true }}
          onFinish={savePlayer}
        >
          <Form.Item
            label="玩家称呼"
            name="displayName"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label="玩家状态"
            name="isActive"
            valuePropName="checked"
            tooltip="停用后，该玩家的全部角色不再进入新排表候选池；历史排表不受影响"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="人员导入记录"
        open={historyOpen}
        width={900}
        footer={null}
        onCancel={() => {
          setHistoryOpen(false);
          setHistoryDetail(null);
        }}
      >
        <Table<ImportBatchSummary>
          size="small"
          loading={historyLoading && !historyDetail}
          rowKey="id"
          dataSource={history}
          pagination={{
            current: historyPage,
            pageSize: 10,
            total: historyTotal,
            showSizeChanger: false,
            hideOnSinglePage: true,
            onChange: (page) => void loadHistory(page),
          }}
          columns={[
            { title: "文件", dataIndex: "filename", ellipsis: true },
            {
              title: "结果",
              width: 90,
              render: (_, item) => (item.status === "COMMITTED" ? "已同步" : "仅预览"),
            },
            {
              title: "变更摘要",
              render: (_, item) =>
                `新增 ${item.summary.create} · 更新 ${item.summary.update} · 停用 ${item.summary.deactivate_players + item.summary.deactivate}`,
            },
            {
              title: "时间",
              width: 180,
              render: (_, item) => new Date(item.created_at).toLocaleString("zh-CN"),
            },
            {
              title: "操作",
              width: 90,
              render: (_, item) => (
                <Button type="link" size="small" onClick={() => void openHistoryDetail(item.id)}>
                  查看详情
                </Button>
              ),
            },
          ]}
        />
        {historyDetail && (
          <div className="personnel-import-history-detail">
            <Typography.Title level={5}>{historyDetail.filename} 的变更明细</Typography.Title>
            {(historyDetail.change_details ?? []).length ? (
              <ImportChangeTable changes={historyDetail.change_details ?? []} />
            ) : (
              <Typography.Text type="secondary">该批次没有人员变更</Typography.Text>
            )}
          </div>
        )}
      </Modal>
      <Modal
        title={
          editingCharacter
            ? `修改 ${characterPlayer?.displayName || ""} 的角色`
            : `为 ${characterPlayer?.displayName || ""} 添加角色`
        }
        className="character-editor-modal"
        width={720}
        open={!!characterPlayer}
        onCancel={closeCharacter}
        onOk={() => characterForm.submit()}
      >
        <Form
          form={characterForm}
          layout="vertical"
          initialValues={{
            roleType: "DAMAGE",
            isTreasureDamage: false,
            isFixedLeadTeamBuffer: false,
            isGroupHunt: false,
            defaultRaidParticipant: true,
            isActive: true,
          }}
          onFinish={saveCharacter}
        >
          <div className="character-form-main-grid">
            <Form.Item
              className="character-profession-field"
              label="职业"
              name="profession"
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
            <Form.Item label="类型" name="roleType">
              <Segmented
                className="character-role-type"
                block
                options={[
                  { label: "C", value: "DAMAGE" },
                  { label: "奶", value: "BUFFER" },
                ]}
              />
            </Form.Item>
            <Form.Item
              label={characterRole === "BUFFER" ? "奶量（万）" : "伤害（亿）"}
              name="score"
              rules={[{ required: true }]}
            >
              <InputNumber
                min={0}
                precision={characterRole === "DAMAGE" ? 0 : 2}
                className="full-width"
              />
            </Form.Item>
          </div>

          <Typography.Text className="character-form-section-title">
            角色标签
          </Typography.Text>
          <div className="character-form-switch-grid">
            {characterRole === "DAMAGE" ? (
              <>
                <CharacterSwitchField label="秘宝 C">
                  <Form.Item name="isTreasureDamage" valuePropName="checked" noStyle>
                    <Switch />
                  </Form.Item>
                </CharacterSwitchField>
                <CharacterSwitchField label="群猎 C">
                  <Form.Item name="isGroupHunt" valuePropName="checked" noStyle>
                    <Switch />
                  </Form.Item>
                </CharacterSwitchField>
              </>
            ) : (
              <CharacterSwitchField label="固定红队奶">
                <Form.Item
                  name="isFixedLeadTeamBuffer"
                  valuePropName="checked"
                  noStyle
                >
                  <Switch />
                </Form.Item>
              </CharacterSwitchField>
            )}
          </div>

          <Typography.Text className="character-form-section-title">
            参与设置
          </Typography.Text>
          <div className="character-form-switch-grid">
            <CharacterSwitchField label="默认加入新排表">
              <Form.Item name="defaultRaidParticipant" valuePropName="checked" noStyle>
                <Switch />
              </Form.Item>
            </CharacterSwitchField>
            <CharacterSwitchField label="角色启用">
              <Form.Item name="isActive" valuePropName="checked" noStyle>
                <Switch />
              </Form.Item>
            </CharacterSwitchField>
          </div>
        </Form>
      </Modal>
    </section>
  );
}

function ImportChangeTable({ changes }: { changes: ImportChange[] }) {
  return (
    <Table<ImportChange>
      className="personnel-import-changes"
      size="small"
      rowKey={(row) => `${row.action}-${row.row_no ?? "existing"}-${row.player_name}-${row.profession ?? ""}`}
      dataSource={changes}
      pagination={{ pageSize: 6, hideOnSinglePage: true, size: "small" }}
      columns={[
        {
          title: "动作",
          width: 110,
          render: (_, row) => importActionLabel(row.action),
        },
        { title: "玩家", dataIndex: "player_name" },
        { title: "职业", dataIndex: "profession", render: (value) => value || "—" },
        {
          title: "Excel 行",
          dataIndex: "row_no",
          width: 90,
          render: (value) => value ?? "—",
        },
        { title: "变更内容", render: (_, row) => row.fields.join("、") || "—" },
      ]}
    />
  );
}

function importActionLabel(action: ImportChange["action"]): ReactNode {
  const labels: Record<ImportChange["action"], { color: string; text: string }> = {
    CREATE: { color: "green", text: "新增" },
    UPDATE: { color: "blue", text: "更新" },
    REACTIVATE: { color: "cyan", text: "恢复" },
    DEACTIVATE_PLAYER: { color: "red", text: "停用玩家" },
    DEACTIVATE_CHARACTER: { color: "orange", text: "停用角色" },
    REORDER: { color: "default", text: "调整顺序" },
  };
  const label = labels[action];
  return <Tag color={label.color}>{label.text}</Tag>;
}

function CharacterSwitchField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="character-switch-field">
      <Typography.Text>{label}</Typography.Text>
      {children}
    </div>
  );
}

interface SortablePlayerPanelProps {
  player: Player;
  dragDisabled: boolean;
  canEdit: boolean;
  onAddCharacter: (player: Player) => void;
  onEditPlayer: (player: Player) => void;
  onDeletePlayer: (player: Player) => void;
  onEditCharacter: (player: Player, character: Character) => void;
  onDeleteCharacter: (character: Character) => void;
  onCharacterDragEnd: (playerId: string, event: DragEndEvent) => void;
}

function SortablePlayerPanel({
  player,
  dragDisabled,
  canEdit,
  onAddCharacter,
  onEditPlayer,
  onDeletePlayer,
  onEditCharacter,
  onDeleteCharacter,
  onCharacterDragEnd,
}: SortablePlayerPanelProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: player.id, disabled: dragDisabled });
  const characterSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  return (
    <div
      ref={setNodeRef}
      className={`sortable-player${isDragging ? " is-dragging" : ""}`}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <Collapse
        className="personnel-player-collapse"
        items={[
          {
            key: player.id,
            label: (
              <Space>
                <Typography.Text strong>{player.displayName}</Typography.Text>
                <Tag>{player.characters.length} 个角色</Tag>
                {!player.isActive && <Tag>已停用</Tag>}
              </Space>
            ),
            extra: (
              <Space size={2} onClick={(event) => event.stopPropagation()}>
                <Button
                  type="text"
                  size="small"
                  className="sort-handle"
                  icon={<HolderOutlined />}
                  disabled={dragDisabled}
                  {...attributes}
                  {...listeners}
                  aria-label={`拖动玩家 ${player.displayName}`}
                  title="拖动调整玩家顺序"
                />
                <Button
                  type="link"
                  size="small"
                  icon={<PlusOutlined />}
                  disabled={!canEdit || !player.isActive}
                  onClick={() => onAddCharacter(player)}
                >
                  添加角色
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  disabled={!canEdit}
                  onClick={() => onEditPlayer(player)}
                >
                  修改
                </Button>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={!canEdit}
                  onClick={() => onDeletePlayer(player)}
                >
                  删除
                </Button>
              </Space>
            ),
            children: player.characters.length ? (
              <DndContext
                sensors={characterSensors}
                collisionDetection={closestCenter}
                onDragEnd={(event) => void onCharacterDragEnd(player.id, event)}
              >
                <SortableContext
                  items={player.characters.map((character) => character.id)}
                  strategy={rectSortingStrategy}
                >
                  <div className="character-grid">
                    {player.characters.map((character) => (
                      <SortableCharacterCard
                        key={character.id}
                        character={character}
                        dragDisabled={dragDisabled}
                        canEdit={canEdit}
                        onEdit={() => onEditCharacter(player, character)}
                        onDelete={() => onDeleteCharacter(character)}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            ) : (
              <Typography.Text type="secondary">暂无角色</Typography.Text>
            ),
          },
        ]}
      />
    </div>
  );
}

interface SortableCharacterCardProps {
  character: Character;
  dragDisabled: boolean;
  canEdit: boolean;
  onEdit: () => void;
  onDelete: () => void;
}

function SortableCharacterCard({
  character,
  dragDisabled,
  canEdit,
  onEdit,
  onDelete,
}: SortableCharacterCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: character.id, disabled: dragDisabled });
  const scoreLabel = character.roleType === "DAMAGE" ? "伤害" : "奶量";
  const scoreUnit = character.roleType === "DAMAGE" ? "亿" : "万";
  const rawScore = character.damageScore ?? character.bufferScore;
  const scoreValue =
    character.roleType === "DAMAGE" && rawScore !== null
      ? Math.round(Number(rawScore)).toString()
      : rawScore ?? "—";
  const characterActions: MenuProps["items"] = [
    {
      key: "edit",
      icon: <EditOutlined />,
      label: "修改角色",
      onClick: onEdit,
    },
  ];
  characterActions.push(
    { type: "divider" },
    {
      key: "delete",
      danger: true,
      icon: <DeleteOutlined />,
      label: "永久删除",
      onClick: onDelete,
    },
  );
  return (
    <div
      ref={setNodeRef}
      className={`sortable-character${isDragging ? " is-dragging" : ""}`}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <Card
        size="small"
        className={`character-card${character.isActive ? "" : " is-inactive"}`}
      >
        <div className="character-card-header">
          <Space size={6} wrap>
            <Tag
              className={`personnel-role-tag ${
                character.roleType === "DAMAGE"
                  ? "personnel-role-tag-damage"
                  : "personnel-role-tag-buffer"
              }`}
            >
              {character.roleType === "DAMAGE" ? "C" : "奶"}
            </Tag>
            <Typography.Text strong className="character-card-name">
              {character.profession}
            </Typography.Text>
            {character.isTreasureDamage && (
              <Tag className="character-trait-tag character-trait-treasure">秘宝 C</Tag>
            )}
            {character.isFixedLeadTeamBuffer && (
              <Tag className="character-trait-tag character-trait-fixed-buffer">
                固定红队奶
              </Tag>
            )}
            {character.isGroupHunt && (
              <Tag className="character-trait-tag character-trait-group-hunt">群猎 C</Tag>
            )}
          </Space>
          <Space size={2}>
            <Button
              type="text"
              size="small"
              className="sort-handle"
              icon={<HolderOutlined />}
              disabled={dragDisabled}
              {...attributes}
              {...listeners}
              aria-label={`拖动角色 ${character.profession}`}
              title="拖动调整角色顺序"
            />
            <Dropdown menu={{ items: characterActions }} trigger={["click"]}>
              <Button
                type="text"
                size="small"
                icon={<MoreOutlined />}
                disabled={!canEdit}
                aria-label={`管理角色 ${character.profession}`}
              />
            </Dropdown>
          </Space>
        </div>
        <div className="character-card-details">
          <div className="character-card-status" aria-label="角色状态">
            <span className="character-status-item">
              <span
                className={`character-status-dot ${character.isActive ? "is-positive" : "is-negative"}`}
                aria-hidden="true"
              />
              <span>{character.isActive ? "启用" : "停用"}</span>
            </span>
            <span className="character-status-divider" aria-hidden="true" />
            <span className="character-status-item">
              <span
                className={`character-status-dot ${character.defaultRaidParticipant ? "is-positive" : "is-negative"}`}
                aria-hidden="true"
              />
              <span>{character.defaultRaidParticipant ? "参团" : "不参团"}</span>
            </span>
          </div>
          <Typography.Text className="character-card-score">
            <span>{scoreLabel}</span>
            <strong>{scoreValue}</strong>
            <span>{scoreUnit}</span>
          </Typography.Text>
        </div>
      </Card>
    </div>
  );
}
