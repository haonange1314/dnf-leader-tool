import {
  DownloadOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
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
import { api, type ImportBatch, type Player, type User } from "../../api/client";

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
  const [characterPlayer, setCharacterPlayer] = useState<Player | null>(null);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [playerForm] = Form.useForm();
  const [characterForm] = Form.useForm();
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
  const addPlayer = async (values: Record<string, unknown>) => {
    try {
      await api("/players", {
        method: "POST",
        body: JSON.stringify({ ...values, characters: [] }),
      });
      setPlayerOpen(false);
      playerForm.resetFields();
      onSuccess("玩家已添加");
      await load();
    } catch (error) {
      onError(error);
    }
  };
  const addCharacter = async (values: Record<string, unknown>) => {
    if (!characterPlayer) return;
    const { score, ...rest } = values;
    const role = values.roleType;
    const payload = {
      ...rest,
      damageScore: role === "DAMAGE" ? score : null,
      bufferScore: role === "BUFFER" ? score : null,
      isTreasureDamage: role === "DAMAGE" && values.isTreasureDamage,
    };
    try {
      await api(`/players/${characterPlayer.id}/characters`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCharacterPlayer(null);
      characterForm.resetFields();
      onSuccess("角色已添加");
      await load();
    } catch (error) {
      onError(error);
    }
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
            placeholder="搜索玩家或角色"
            onSearch={setSearch}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!canEdit}
            onClick={() => setPlayerOpen(true)}
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
      <Collapse
        className="personnel-list"
        items={players.map((player) => ({
          key: player.id,
          label: (
            <Space>
              <Typography.Text strong>{player.displayName}</Typography.Text>
              <Tag>{player.characters.length} 个角色</Tag>
              {!player.isActive && <Tag>已停用</Tag>}
            </Space>
          ),
          extra: (
            <Button
              size="small"
              disabled={!canEdit}
              onClick={(event) => {
                event.stopPropagation();
                setCharacterPlayer(player);
              }}
            >
              添加角色
            </Button>
          ),
          children: player.characters.length ? (
            <div className="character-grid">
              {player.characters.map((character) => (
                <Card
                  size="small"
                  key={character.id}
                  className="character-card"
                >
                  <Space direction="vertical" size={2}>
                    <Space>
                      <Tag
                        color={
                          character.roleType === "DAMAGE" ? "volcano" : "blue"
                        }
                      >
                        {character.roleType === "DAMAGE" ? "C" : "奶"}
                      </Tag>
                      <Typography.Text strong>{character.name}</Typography.Text>
                      {character.isTreasureDamage && (
                        <Tag color="gold">秘宝</Tag>
                      )}
                    </Space>
                    <Typography.Text type="secondary">
                      {character.profession} ·{" "}
                      {character.damageScore || character.bufferScore}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {character.defaultRaidParticipant
                        ? "默认参团"
                        : "按需参团"}
                    </Typography.Text>
                  </Space>
                </Card>
              ))}
            </div>
          ) : (
            <Typography.Text type="secondary">暂无角色</Typography.Text>
          ),
        }))}
      />
      <Modal
        title="新增玩家"
        open={playerOpen}
        onCancel={() => setPlayerOpen(false)}
        onOk={() => playerForm.submit()}
      >
        <Form
          form={playerForm}
          layout="vertical"
          initialValues={{ isActive: true }}
          onFinish={addPlayer}
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
        title={`为 ${characterPlayer?.displayName || ""} 添加角色`}
        open={!!characterPlayer}
        onCancel={() => setCharacterPlayer(null)}
        onOk={() => characterForm.submit()}
      >
        <Form
          form={characterForm}
          layout="vertical"
          initialValues={{
            roleType: "DAMAGE",
            isTreasureDamage: false,
            defaultRaidParticipant: true,
            isActive: true,
          }}
          onFinish={addCharacter}
        >
          <Form.Item label="角色名" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
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
            <Switch />
          </Form.Item>
          <Form.Item
            label="默认参团"
            name="defaultRaidParticipant"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Form.Item label="备注" name="note">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
