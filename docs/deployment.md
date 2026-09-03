# 生产部署与数据恢复

本文适用于单台 Linux 服务器上的 Docker Compose 部署。公网入口由 Caddy 提供自动
HTTPS，业务容器和 PostgreSQL 不映射公网端口。

## 1. 前置条件

- 域名 A/AAAA 记录指向服务器。
- 防火墙仅对公网开放 TCP 80、TCP 443 和 UDP 443；SSH 只允许受信来源。
- 安装受支持的 Docker Engine 和 Docker Compose 插件。
- 服务器时间同步正常，并准备数据库卷之外的加密备份目录或远端对象存储。

## 2. 生产配置

```bash
cp infra/production.env.example .env.production
chmod 600 .env.production
```

至少替换 `PUBLIC_DOMAIN`、数据库密码、`CONTAINER_DATABASE_URL` 和 Owner 密码。
URL 中的保留字符必须百分号编码。生产叠加配置会强制：

- `ENVIRONMENT=production`、`COOKIE_SECURE=true` 和精确 HTTPS CORS 来源；
- 登录页不编译本地示例账号；
- PostgreSQL、API 和 Web 不发布宿主机端口；
- Caddy 暴露 80/443、申请证书并设置 HSTS、CSP 等安全响应头；
- 后端拒绝 localhost、HTTP CORS、示例数据库密码或示例 Owner 密码。

提交前检查最终配置，不要把 `.env.production` 加入 Git：

```bash
make prod-config
git status --short
```

## 3. 启动与验收

```bash
make prod-up
make prod-logs
```

首次启动会依次执行 Alembic 迁移、内置副本种子和 Owner 幂等初始化。随后检查：

```bash
curl --fail --silent --show-error https://你的域名/api/v1/health/ready
curl --fail --head https://你的域名/
```

浏览器验收登录、多账号权限、排表编辑租约、发布和导出。确认响应包含 HSTS，且
HTTP 自动跳转到 HTTPS。生产 API 只通过 Caddy 访问，不应直接暴露 8000 端口；
PostgreSQL 也不应暴露 5432 端口。

代码准备发布时先运行完整本地验收与生产配置校验；部署后再对真实域名执行只读检查：

```bash
make release-check
make prod-smoke PUBLIC_BASE_URL=https://你的域名
```

`release-check` 包含静态检查、前后端测试、生产构建、隔离数据库迁移/备份恢复、求解质量与
性能基线，以及 Playwright 浏览器闭环；`prod-smoke` 检查就绪探针、HTTP 到 HTTPS 跳转、
HSTS、CSP 和 `X-Content-Type-Options`。如启用自然语言规则，另运行一次
`make test-deepseek-live` 验证正式服务器能访问所配置模型，该命令会产生一次真实 API 调用。

## 4. 备份

默认备份目录是仓库下被 Git 忽略的 `backups/`，生产环境应改为数据库卷之外的挂载点：

```bash
BACKUP_DIR=/srv/dnf-leader-backups make backup
```

脚本使用 PostgreSQL 自定义格式、无 owner/privilege 信息的 `pg_dump`，先写 `.partial`
临时文件，成功后原子改名。建议每天执行并把结果同步到异机或对象存储；至少保留
7 个日备份、4 个周备份和 6 个按月备份。定期校验文件大小、哈希和远端可读性。

## 5. 恢复与演练

恢复会先校验归档并恢复到隔离临时数据库；只有临时库结构检查通过后才停止 API，原生产
数据库会保留到新数据库通过迁移版本和就绪探针检查。先确认备份文件、维护窗口和最近一次
额外备份，再执行：

```bash
BACKUP_FILE=/srv/dnf-leader-backups/dnf-leader-YYYYMMDDTHHMMSSZ.dump make restore
```

脚本要求显式确认标记，直接调用时使用：

```bash
CONFIRM_RESTORE=dnf_leader \
ENV_FILE=.env.production \
sh scripts/restore-db.sh /绝对路径/backup.dump
```

恢复过程中若切换或健康检查失败，API 会保持停止，脚本会输出保留的旧数据库名称，禁止在
未确认数据库状态前直接启动服务。恢复后必须检查 Alembic 当前版本、就绪探针、用户/排表/发布版本数量，并完成一次登录、
历史版本预览和导出。`make test-stack` 会在隔离 PostgreSQL 中自动执行一次 dump、恢复到
全新数据库并比较关键表数量，可作为每次发布前的恢复演练。

## 6. 升级与回滚

升级前先备份，然后拉取已审核的提交并执行 `make prod-up`。应用镜像回滚不能替代数据库
回滚：如果新迁移不向后兼容，优先恢复升级前备份。发布版本和分享链接的历史数据不得
通过手工 SQL 修改。

## 7. 日常运维

- 监控 Caddy、API 和 PostgreSQL 日志、磁盘容量、证书续期和就绪探针。
- 定期检查失败登录、权限拒绝、编辑锁接管和写操作审计记录。
- Owner 或数据库凭据变化后同步更新受限的 `.env.production`，不要写入命令历史或 Git。
- 离职/失效账号应立即停用；系统会撤销其会话并清除其编辑租约。
- 每季度至少执行一次从异机备份恢复到全新数据库的演练并记录恢复时间。
