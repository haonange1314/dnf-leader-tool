import { EyeOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Card, Descriptions, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, type AuditLog } from "../../api/client";

interface Props {
  onError: (error: unknown) => void;
}

const ACTION_LABELS: Record<string, string> = {
  AUTH_LOGIN: "账号登录",
  HTTP_POST: "新增/执行",
  HTTP_PATCH: "修改",
  HTTP_PUT: "更新",
  HTTP_DELETE: "删除/撤销",
};

const PAGE_SIZE = 20;

export function AuditLogPage({ onError }: Props) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [outcome, setOutcome] = useState<string | undefined>();
  const [action, setAction] = useState<string | undefined>();
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String((page - 1) * PAGE_SIZE),
      });
      if (search.trim()) query.set("search", search.trim());
      if (outcome) query.set("outcome", outcome);
      if (action) query.set("action", action);
      const result = await api<{ items: AuditLog[]; total: number }>(`/audit-logs?${query}`);
      setLogs(result.items);
      setTotal(result.total);
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [page, outcome, action]);

  return (
    <section>
      <div className="section-heading">
        <div><Typography.Title level={2}>操作日志</Typography.Title><Typography.Text type="secondary">独立检索登录和已认证写操作，日志只读且不可修改</Typography.Text></div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
      </div>
      <Card className="module-card" size="small">
        <Space wrap className="admin-filter-bar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="请求 ID、资源 ID 或 IP" value={search} onChange={(event) => setSearch(event.target.value)} onPressEnter={() => { setPage(1); void load(); }} style={{ width: 250 }} />
          <Button onClick={() => { setPage(1); void load(); }}>查询</Button>
          <Select allowClear placeholder="全部结果" value={outcome} onChange={(value) => { setPage(1); setOutcome(value); }} options={[{ value: "SUCCESS", label: "成功" }, { value: "FAILURE", label: "失败" }]} style={{ width: 120 }} />
          <Select allowClear placeholder="全部动作" value={action} onChange={(value) => { setPage(1); setAction(value); }} options={Object.entries(ACTION_LABELS).map(([value, label]) => ({ value, label }))} style={{ width: 140 }} />
        </Space>
        <Table<AuditLog>
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={logs}
          scroll={{ x: 1060 }}
          pagination={{ current: page, pageSize: PAGE_SIZE, total, showSizeChanger: false, showTotal: (count) => `共 ${count} 条`, onChange: setPage }}
          columns={[
            { title: "时间", dataIndex: "createdAt", width: 170, render: (value: string) => new Date(value).toLocaleString() },
            { title: "账号", dataIndex: "actorUsername", width: 140, render: (value: string | null) => value ?? "匿名" },
            { title: "动作", dataIndex: "action", width: 130, render: (value: string) => ACTION_LABELS[value] ?? value },
            { title: "结果", dataIndex: "outcome", width: 90, render: (value: string) => <Tag color={value === "SUCCESS" ? "green" : "red"}>{value === "SUCCESS" ? "成功" : "失败"}</Tag> },
            { title: "资源", width: 190, render: (_, log) => [log.resourceType, log.resourceId].filter(Boolean).join(" / ") || "—" },
            { title: "IP", dataIndex: "ipAddress", width: 130, render: (value: string | null) => value ?? "—" },
            { title: "请求 ID", dataIndex: "requestId", ellipsis: true },
            { title: "详情", fixed: "right", width: 76, render: (_, log) => <Button type="link" icon={<EyeOutlined />} onClick={() => setSelected(log)}>查看</Button> },
          ]}
        />
      </Card>
      <Modal title="操作日志详情" open={selected !== null} onCancel={() => setSelected(null)} footer={<Button onClick={() => setSelected(null)}>关闭</Button>} width={720}>
        {selected ? <><Descriptions size="small" column={2} bordered items={[
          { key: "time", label: "时间", children: new Date(selected.createdAt).toLocaleString() },
          { key: "user", label: "账号", children: selected.actorUsername ?? "匿名" },
          { key: "action", label: "动作", children: ACTION_LABELS[selected.action] ?? selected.action },
          { key: "result", label: "结果", children: selected.outcome === "SUCCESS" ? "成功" : "失败" },
          { key: "request", label: "请求 ID", children: selected.requestId, span: 2 },
          { key: "resource", label: "资源", children: [selected.resourceType, selected.resourceId].filter(Boolean).join(" / ") || "—", span: 2 },
        ]} /><Typography.Title level={5}>上下文</Typography.Title><pre className="audit-details">{JSON.stringify(selected.details, null, 2)}</pre></> : null}
      </Modal>
    </section>
  );
}
