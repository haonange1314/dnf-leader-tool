# DNF 团长排表工具

面向 DNF 国服 PC 端团长的人员管理与智能排表网站。项目通过版本化副本配置定义人数、队伍和分队规则，再结合玩家可用波次、角色强度及特殊角色标签自动生成多波排表。

> 当前状态：阶段 4.2 编辑与导出收尾已完成。已支持拖拽/交换/占位替换、角色/位置/波次锁定、撤销恢复、总览/单波视图、发布预检、不可变发布版本、历史预览/恢复/复制、分享链接有效期和撤销管理，以及带草稿水印或基于发布版本的 PNG 长图、Excel 和文本导出；下一步进入阶段 5 公网化。

## 核心能力

- **副本管理**：配置默认波数、队伍数量、每队人数、合法组成、强度顺序和特殊角色规则。
- **人员管理**：维护玩家及其多个角色，支持手动录入和 Excel 批量导入。
- **智能排表**：根据角色次数、玩家可用波次、C 伤害、奶增益量和秘宝 C 自动排队。
- **人工微调**：支持拖拽、交换、锁定、撤销恢复和局部重新生成。
- **版本历史**：发布不可变排表快照，支持复制旧排表开启全新次数周期。
- **分享导出**：支持可过期、可撤销的只读链接，以及 PNG 长图、Excel 和纯文本；草稿导出强制显示水印。

## 默认 12 人团本规则

系统将内置一个 12 人团本副本版本：

| 规则 | 默认值 |
| --- | --- |
| 默认波数 | 12，可动态增减 |
| 每波人数 | 12 |
| 队伍 | 红、黄、绿三队 |
| 每队人数 | 4 |
| 优先组成 | 3C1奶 |
| 备用组成 | C 不足且奶富余时允许 2C2奶 |
| 特殊角色 | 每波一个秘宝 C，进入红队 |
| 队伍强度 | 红队 ≥ 黄队 ≥ 绿队 |
| 跨波目标 | 各波总体实力尽量接近 |
| 空位策略 | 优先填满前面的波次 |

同一角色在一张排表中最多使用一次；同一玩家在同一波最多使用一个角色，但可以在不同波使用不同角色。

## 可扩展副本模型

人数和队伍规则不会写死在页面或求解器中。每个副本通过不可变版本定义：

- 队伍数量、名称、颜色、顺序和人数。
- 每支队伍允许的角色组成及优先级。
- 特殊角色的标签、数量和目标队伍。
- 队伍强度顺序、跨波平衡和待补策略。
- 默认波数、允许波数范围和评分公式版本。

排表绑定具体副本版本，因此发布新副本规则不会改变旧排表或历史导出。该模型可以表达单队 4 人等结构；军团本的人工互带工作流将在后续版本实现。

## 技术架构

```mermaid
flowchart LR
    Browser["浏览器"] --> Web["React + TypeScript"]
    Web --> API["FastAPI"]
    API --> DB[("PostgreSQL")]
    API --> Solver["OR-Tools CP-SAT"]
    API --> Excel["Excel 导入导出"]
    API --> Export["Pillow PNG 长图"]
```

| 层级 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、Ant Design、dnd-kit |
| 后端 | FastAPI、Pydantic、SQLAlchemy、Alembic |
| 智能排表 | OR-Tools CP-SAT |
| 数据库 | PostgreSQL |
| Excel | openpyxl |
| 长图 | Pillow |
| 部署 | Docker Compose |
| 测试 | pytest、Vitest、隔离 Docker/PostgreSQL 冒烟测试 |

MVP 采用模块化单体架构，不引入 Redis、消息队列或微服务。开发阶段在本机通过 Docker Compose 运行，后续复用同一容器结构部署到公网服务器。

## 项目文档

- [需求设计文档](docs/design.md)：产品范围、业务规则、页面流程和验收标准。
- [技术设计文档](docs/technical-design.md)：系统架构、PostgreSQL、API、求解器、测试和部署方案。

当前文档版本均为 v0.2。

## 快速开始

### 环境要求

- Node.js 24、pnpm 11。
- Python 3.12、uv。
- Docker Desktop（包含 Docker Compose）。

首次启动：

```bash
make bootstrap
make up
```

`make bootstrap` 会在 `.env` 不存在时从 `.env.example` 创建本地配置，并按锁文件安装依赖。`make up` 会构建并后台启动 PostgreSQL、API 和 Web；API 容器会自动执行 Alembic 迁移和幂等种子。

启动后可访问：

- Web：<http://localhost:5173>
- API 文档：<http://localhost:8000/docs>
- 存活探针：<http://localhost:8000/api/v1/health/live>
- 就绪探针（检查 PostgreSQL）：<http://localhost:8000/api/v1/health/ready>

本地示例账号由 `.env` 中的 `BOOTSTRAP_OWNER_USERNAME` 和
`BOOTSTRAP_OWNER_PASSWORD` 幂等初始化。示例值为 `admin / change-me-now`，首次用于实际数据前请修改密码；公网环境不得使用示例凭据。
本地 Compose 默认会在登录页展示并预填这组账号；设置
`VITE_SHOW_DEV_LOGIN=false` 后重新构建 Web 即可关闭，公网环境必须关闭。

常用命令：

```bash
make test          # 后端 pytest + 前端 Vitest
make check         # 静态检查、前后端测试及隔离 PostgreSQL 全栈验收
make test-stack    # 验证迁移、种子、编辑、发布、导出、鉴权和反向代理
make solver-poc    # 运行默认 12 波团本和自定义单队 4 人 CP-SAT PoC
make migrate       # 本机对 DATABASE_URL 执行数据库迁移
make seed          # 幂等写入内置 12 人团本及评分公式
make init-owner    # 交互式创建首个 Owner（未使用环境变量时提示输入）
make logs          # 跟踪三个容器日志
make down          # 停止容器，保留 PostgreSQL 数据卷
```

本地 `.env` 中的 `DATABASE_URL` 供宿主机命令使用，连接 `localhost`；`CONTAINER_DATABASE_URL` 供 API 容器使用，连接 Compose 服务名 `db`。两者的用户名、密码和数据库名必须与 PostgreSQL 配置保持一致；用于公网环境前必须替换示例密码。数据库端口只绑定到 `127.0.0.1`。

不使用 Docker 时，可以分别启动开发服务：

```bash
pnpm dev
cd backend && uv run uvicorn app.main:app --reload
```

## 开发进度

- [x] 需求梳理
- [x] 技术设计
- [x] 副本扩展模型
- [x] 初始化 React、FastAPI 和 Docker Compose 工程
- [x] 建立首批副本 PostgreSQL Schema、迁移和种子
- [x] 完成 OR-Tools 阶段 0 算法 PoC
- [x] 建立 Owner 登录和服务端会话
- [x] 开发副本版本、人员管理及 Excel 导入基础闭环
- [x] 建立排表、参团快照、玩家偏好、波次、队伍和位置 Schema
- [x] 完成排表创建/复制、波数调整、参团选择和角色快照同步
- [x] 完成玩家波次偏好、结构化预检查和只读空排表编辑器
- [x] 开发 OR-Tools 自动排表、锁定保留、求解诊断和生成记录
- [x] 开发拖拽编辑器、发布版本、只读分享和多格式导出
- [x] 完善发布预检、历史版本预览/复制、分享管理和草稿水印导出
- [ ] 完成多账号、角色权限和单编辑会话锁（区别于现有角色/位置/波次锁定）
- [ ] 完成 HTTPS、CSRF、限流、审计和生产部署配置
- [ ] 完成 PostgreSQL 备份恢复演练、正式端到端测试和性能验收

## 建议实施顺序

```text
工程初始化与算法 PoC
→ 副本管理
→ 人员管理与 Excel 导入
→ 排表基础与预检查
→ OR-Tools 自动排表
→ 拖拽微调与角色/位置/波次锁定
→ 发布版本与导出
→ 多账号、单编辑会话锁与公网部署
```

## 当前目录结构

```text
dnf-leader-tool/
├── frontend/              # React 应用
├── backend/               # FastAPI、领域逻辑、模型、迁移和求解器
├── docs/                  # 需求和技术文档
├── infra/                 # 容器及反向代理配置
├── compose.yaml
├── .env.example
├── Makefile
└── README.md
```

## 数据与部署约定

- PostgreSQL 数据使用持久化卷，生产环境不暴露数据库公网端口。
- `.env`、密钥、数据库文件、上传文件、导出文件和本地备份不会提交到 Git。
- `pnpm-lock.yaml`、`uv.lock`、Alembic 迁移和 `.env.example` 应提交到仓库。
- 已发布副本版本和排表版本保持不可变。
- 公网部署前必须完成数据库备份与恢复演练。
