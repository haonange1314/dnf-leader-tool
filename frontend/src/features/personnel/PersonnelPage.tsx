import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  HolderOutlined,
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
  Button,
  Card,
  Collapse,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Space,
  Switch,
  Tag,
  Typography,
  Upload,
} from "antd";
import { useEffect, useState } from "react";
import {
  api,
  type Character,
  type ImportBatch,
  type Player,
  type User,
} from "../../api/client";

interface Props {
  userRole: User["role"];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

export function PersonnelPage({ userRole, onError, onSuccess }: Props) {
  const canEdit = userRole !== "VIEWER";
  const [players, setPlayers] = useState<Player[]>([]);
  const [search, setSearch] = useState("");
  const [playerOpen, setPlayerOpen] = useState(false);
  const [editingPlayer, setEditingPlayer] = useState<Player | null>(null);
  const [characterPlayer, setCharacterPlayer] = useState<Player | null>(null);
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
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
        (
          await api<{ items: Player[] }>(
            `/players${search ? `?search=${encodeURIComponent(search)}` : ""}`,
          )
        ).items,
      );
    } catch (error) {
      onError(error);
    }
  };
  useEffect(() => {
    void load();
  }, [search]);
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
  const deactivatePlayer = (player: Player) => {
    Modal.confirm({
      title: `停用玩家“${player.displayName}”？`,
      content: "玩家及其角色不会进入新排表，历史排表数据仍会保留。",
      okText: "确认停用",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api(`/players/${player.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              displayName: player.displayName,
              isActive: false,
            }),
          });
          onSuccess("玩家已停用");
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
    const payload = {
      ...rest,
      damageScore: role === "DAMAGE" ? score : null,
      bufferScore: role === "BUFFER" ? score : null,
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
  const deactivateCharacter = (character: Character) => {
    Modal.confirm({
      title: `停用角色“${character.profession}”？`,
      content: "该角色不会进入新排表，历史排表中的角色快照仍会保留。",
      okText: "确认停用",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api(`/characters/${character.id}/deactivate`, {
            method: "POST",
          });
          onSuccess("角色已停用");
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
    try {
      const result = await api<ImportBatch>("/imports/characters/preview", {
        method: "POST",
        body,
      });
      setBatch(result);
      onSuccess("导入预览已生成");
    } catch (error) {
      onError(error);
    }
    return false;
  };
  const commit = async () => {
    if (!batch) return;
    try {
      const result = await api<ImportBatch>(
        `/imports/characters/${batch.id}/commit`,
        { method: "POST" },
      );
      setBatch(result);
      onSuccess("人员数据已导入");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const reorderPlayers = async ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id || search || sortPending) return;
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
    if (!over || active.id === over.id || search || sortPending) return;
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
        <Space>
          <Input.Search
            allowClear
            placeholder="搜索玩家或职业"
            onSearch={setSearch}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!canEdit}
            onClick={openCreatePlayer}
          >
            新增玩家
          </Button>
        </Space>
      </div>
      <Card className="import-strip">
        <Space wrap>
          <Button
            icon={<DownloadOutlined />}
            href="/api/v1/imports/characters/template"
          >
            下载 Excel 模板
          </Button>
          <Upload disabled={!canEdit} accept=".xlsx" showUploadList={false} beforeUpload={preview}>
            <Button disabled={!canEdit} icon={<UploadOutlined />}>上传并预览</Button>
          </Upload>
          {batch && (
            <>
              <Tag color={batch.summary.error ? "red" : "blue"}>
                新增 {batch.summary.create} · 更新 {batch.summary.update} · 忽略{" "}
                {batch.summary.ignore} · 错误 {batch.summary.error}
              </Tag>
              <Button
                type="primary"
                disabled={
                  !canEdit || batch.summary.error > 0 || batch.status !== "PREVIEWED"
                }
                onClick={commit}
              >
                确认导入
              </Button>
              {batch.summary.error > 0 && (
                <Button
                  href={`/api/v1/imports/characters/${batch.id}/errors.xlsx`}
                >
                  下载错误
                </Button>
              )}
            </>
          )}
        </Space>
      </Card>
      <Typography.Text type="secondary" className="personnel-sort-hint">
        {search
          ? "搜索结果中暂不支持排序，清空搜索后可继续拖拽"
          : "拖动手柄调整玩家顺序；展开玩家后可拖动角色卡片排序"}
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
                dragDisabled={!canEdit || Boolean(search) || sortPending}
                canEdit={canEdit}
                onAddCharacter={openCreateCharacter}
                onEditPlayer={openEditPlayer}
                onDeactivatePlayer={deactivatePlayer}
                onEditCharacter={openEditCharacter}
                onDeactivateCharacter={deactivateCharacter}
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
          <Form.Item label="启用" name="isActive" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={
          editingCharacter
            ? `修改 ${characterPlayer?.displayName || ""} 的角色`
            : `为 ${characterPlayer?.displayName || ""} 添加角色`
        }
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
          <Form.Item
            label="职业"
            name="profession"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="类型" name="roleType">
            <Radio.Group
              options={[
                { label: "C", value: "DAMAGE" },
                { label: "奶", value: "BUFFER" },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="伤害 / 增益评分"
            name="score"
            rules={[{ required: true }]}
          >
            <InputNumber min={0} precision={2} className="full-width" />
          </Form.Item>
          <Form.Item
            label="秘宝 C"
            name="isTreasureDamage"
            valuePropName="checked"
          >
            <Switch disabled={characterRole !== "DAMAGE"} />
          </Form.Item>
          <Form.Item
            label="固定红队奶"
            name="isFixedLeadTeamBuffer"
            valuePropName="checked"
            tooltip="自动排表时固定到副本定义中强度排名最高的队伍"
          >
            <Switch disabled={characterRole !== "BUFFER"} />
          </Form.Item>
          <Form.Item
            label="群猎"
            name="isGroupHunt"
            valuePropName="checked"
            tooltip="保存为角色标记，暂不自动推断组队规则"
          >
            <Switch disabled={characterRole !== "DAMAGE"} />
          </Form.Item>
          <Form.Item
            label="默认参团"
            name="defaultRaidParticipant"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item label="启用" name="isActive" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}

interface SortablePlayerPanelProps {
  player: Player;
  dragDisabled: boolean;
  canEdit: boolean;
  onAddCharacter: (player: Player) => void;
  onEditPlayer: (player: Player) => void;
  onDeactivatePlayer: (player: Player) => void;
  onEditCharacter: (player: Player, character: Character) => void;
  onDeactivateCharacter: (character: Character) => void;
  onCharacterDragEnd: (playerId: string, event: DragEndEvent) => void;
}

function SortablePlayerPanel({
  player,
  dragDisabled,
  canEdit,
  onAddCharacter,
  onEditPlayer,
  onDeactivatePlayer,
  onEditCharacter,
  onDeactivateCharacter,
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
                  size="small"
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
                {player.isActive && (
                  <Button
                    type="link"
                    size="small"
                    icon={<DeleteOutlined />}
                    disabled={!canEdit}
                    onClick={() => onDeactivatePlayer(player)}
                  >
                    停用
                  </Button>
                )}
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
                        onDeactivate={() => onDeactivateCharacter(character)}
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
  onDeactivate: () => void;
}

function SortableCharacterCard({
  character,
  dragDisabled,
  canEdit,
  onEdit,
  onDeactivate,
}: SortableCharacterCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: character.id, disabled: dragDisabled });
  return (
    <div
      ref={setNodeRef}
      className={`sortable-character${isDragging ? " is-dragging" : ""}`}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <Card size="small" className="character-card">
        <Space direction="vertical" size={2}>
          <Space wrap size={[4, 2]}>
            <Tag color={character.roleType === "DAMAGE" ? "red" : "green"}>
              {character.roleType === "DAMAGE" ? "C" : "奶"}
            </Tag>
            <Typography.Text strong>{character.profession}</Typography.Text>
            {character.isTreasureDamage && <Tag color="purple">秘宝 C</Tag>}
            {character.isFixedLeadTeamBuffer && <Tag color="red">固定红奶</Tag>}
            {character.isGroupHunt && <Tag color="orange">群猎</Tag>}
            {!character.isActive && <Tag>已停用</Tag>}
          </Space>
          <Typography.Text type="secondary">
            {character.roleType === "DAMAGE" ? "伤害" : "奶评分"} ·{" "}
            {character.damageScore ?? character.bufferScore}
          </Typography.Text>
          <Typography.Text type="secondary">
            {character.defaultRaidParticipant ? "默认参团" : "按需参团"}
          </Typography.Text>
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
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              disabled={!canEdit}
              onClick={onEdit}
            >
              修改
            </Button>
            {character.isActive && (
              <Button
                type="link"
                size="small"
                icon={<DeleteOutlined />}
                disabled={!canEdit}
                onClick={onDeactivate}
              >
                停用
              </Button>
            )}
          </Space>
        </Space>
      </Card>
    </div>
  );
}
