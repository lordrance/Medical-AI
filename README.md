# Medical-AI

AI 草稿审核研究平台（V2 FastAPI + Next.js）。

## 功能概览

- 前端：Next.js 14（中文界面）
- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：PostgreSQL（Docker）
- 研究流程：知情同意 → 前测 → 练习案例 → 正式案例 → 后测 → 完成码
- 管理端：汇总、**整库 / ZIP / 单表导出**、LLM 总结接口

### 实验条件（与课题设计一致）

- **guardrail（实验组）**：案例页展示护栏区（AI 总结、AI 风险提示等）。
- **plain（对照组）**：**不展示**护栏区，仅患者消息、病历摘要与 AI 草稿。
- 条件在创建会话时随机分配。

### 案例页近期功能要点（医生端）

- **原样发送**：原「直接发送」已更名为「原样发送」；选择该项时需勾选**核对确认**后方可继续。
- **病历摘要**：默认可**展开 / 收起**，便于阅读长病历。
- **案例编号与进度**：展示当前案例 ID 及正式题进度（练习不计入）。
- **行为数据**：前端通过 `/api/ui-event` 上报面板点击、病历/护栏展开、草稿与源信息切换等；提交时在 `actions.client_stats` 中附带 `interactionMetrics` 汇总。
- **会话关联**：进入案例时调用 `POST /api/case/open`，返回 `casePresentationId`，便于 `ui_events` 与单次审题绑定。

### 数据导出（离线分析）

在后端 `.env` 配置 **`ADMIN_TOKEN`**（生产务必改为长随机串）。管理员可使用：

| 方式 | 接口或入口 | 说明 |
|------|------------|------|
| 整库备份 | `GET /api/admin/export/full-database` | SQLite 返回完整 SQL 文本；PostgreSQL 需服务器安装 `pg_dump`。 |
| 多表 ZIP | `GET /api/admin/export/bundle` | 默认打包研究相关多张表为 CSV；可用 `tables=` 节选。 |
| 单表 | `GET /api/admin/export?table=…&format=csv` | 含 `actions`、`ui_events`、`cases` 等，见 `/docs`。 |

前端：`/admin?token=<ADMIN_TOKEN>` 提供下载入口。详情见 **`backend/README.md`**。

### 端到端数据覆盖自检（可选）

```bash
cd backend && .venv/bin/python -m app.scripts.full_export_scope_demo
```

模拟完整参与流程并校验 ZIP / 整库导出是否包含各业务表（详见脚本输出）。

## LLM 说明（DeepSeek）

- 已接入 DeepSeek Provider（通过环境变量启用）
- 案例接口 `/api/case/{id}` 默认优先调用 LLM 生成 `aiDraft`
- 当 LLM 暂时不可用时，自动回退到种子数据中的 `aiDraft`（保证流程不中断）

## 本地运行（Docker）

1. 在项目根目录准备 `.env`（可从 `.env.example` 复制）
2. 关键变量示例：
   - `LLM_PROVIDER=deepseek`
   - `LLM_DRY_RUN=false`
   - `DEEPSEEK_API_KEY=<your key>`
   - `DEEPSEEK_BASE_URL=https://api.deepseek.com`
   - `DEEPSEEK_MODEL=deepseek-chat`
3. 启动：
   - `docker compose up -d --build`

访问：

- 前端：`http://localhost:3000`
- 后端健康检查：`http://localhost:8000/healthz`

## 开发备注

- 不要提交包含真实密钥的 `.env`
- 若修改了 `Dockerfile` 或依赖，建议重新执行 `docker compose up -d --build`
