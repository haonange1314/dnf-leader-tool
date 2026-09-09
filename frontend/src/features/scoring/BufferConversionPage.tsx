import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, InputNumber, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, type BufferConversionVersion } from "../../api/client";

interface Props {
  permissions: string[];
  onError: (error: unknown) => void;
  onSuccess: (message: string) => void;
}

export function BufferConversionPage({ permissions, onError, onSuccess }: Props) {
  const canEdit = permissions.includes("BUFFER_CONVERSION_WRITE");
  const [current, setCurrent] = useState<BufferConversionVersion | null>(null);
  const [history, setHistory] = useState<BufferConversionVersion[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    try {
      const [active, versions] = await Promise.all([
        api<BufferConversionVersion>("/buffer-conversions/current"),
        api<{ items: BufferConversionVersion[] }>("/buffer-conversions/versions"),
      ]);
      setCurrent(active);
      setHistory(versions.items);
      form.setFieldsValue({ rules: active.rules });
    } catch (error) {
      onError(error);
    }
  };
  useEffect(() => { void load(); }, []);

  const save = async (values: { rules: Array<{ profession: string; multiplier: number }> }) => {
    try {
      await api("/buffer-conversions/versions", {
        method: "POST",
        body: JSON.stringify(values),
      });
      onSuccess("奶量换算配置已保存为新版本");
      await load();
    } catch (error) { onError(error); }
  };

  const runPreview = async (values: { profession: string; standingScore: number }) => {
    try {
      const result = await api<{ actualScore: string }>("/buffer-conversions/preview", {
        method: "POST",
        body: JSON.stringify(values),
      });
      setPreview(result.actualScore);
    } catch (error) { onError(error); }
  };

  return (
    <section className="page-section">
      <div className="page-heading">
        <div><Typography.Title level={2}>奶量换算</Typography.Title><Typography.Text type="secondary">站街奶量 × 职业倍率 = 排表实际奶量，保存后生成不可变的新版本。</Typography.Text></div>
        {current ? <Typography.Text>当前版本 v{current.version}</Typography.Text> : null}
      </div>
      <div className="buffer-conversion-grid">
        <Card title="职业倍率">
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit}>
            <Form.List name="rules">
              {(fields, { add, remove }) => <Space direction="vertical" className="full-width" size={8}>
                {fields.map((field) => <Space key={field.key} align="start" className="full-width">
                  <Form.Item {...field} name={[field.name, "profession"]} rules={[{ required: true, message: "请输入职业" }]}><Input placeholder="职业" /></Form.Item>
                  <Form.Item {...field} name={[field.name, "multiplier"]} rules={[{ required: true, message: "请输入倍率" }]}><InputNumber min={0.00001} max={10} precision={5} step={0.001} placeholder="倍率" /></Form.Item>
                  <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)} aria-label="删除规则" />
                </Space>)}
                {canEdit ? <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ multiplier: 1 })}>添加职业规则</Button> : null}
              </Space>}
            </Form.List>
            {canEdit ? <div className="modal-form-actions"><Button type="primary" htmlType="submit">保存新版本</Button></div> : null}
          </Form>
        </Card>
        <Card title="换算预览">
          <Form layout="vertical" onFinish={runPreview}>
            <Form.Item name="profession" label="职业" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="standingScore" label="站街奶量（万）" rules={[{ required: true }]}><InputNumber min={0} precision={2} className="full-width" /></Form.Item>
            <Space><Button htmlType="submit">计算</Button>{preview !== null ? <Typography.Text strong>实际奶量 {preview} 万</Typography.Text> : null}</Space>
          </Form>
        </Card>
      </div>
      <Card title="版本历史">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={history}
          columns={[
            {
              title: "版本",
              dataIndex: "version",
              width: 110,
              render: (value: number, item: BufferConversionVersion) => (
                <Space size={6}>
                  <span>v{value}</span>
                  {item.isActive ? <Tag color="blue">当前</Tag> : null}
                </Space>
              ),
            },
            {
              title: "职业倍率",
              render: (_: unknown, item: BufferConversionVersion) => (
                <Space size={[4, 4]} wrap>
                  {item.rules.map((rule) => (
                    <Tag key={rule.profession}>
                      {rule.profession} × {rule.multiplier}
                    </Tag>
                  ))}
                </Space>
              ),
            },
            {
              title: "创建时间",
              dataIndex: "createdAt",
              width: 180,
              render: (value: string) => new Date(value).toLocaleString("zh-CN"),
            },
          ]}
          locale={{ emptyText: "暂无换算版本" }}
        />
      </Card>
    </section>
  );
}
