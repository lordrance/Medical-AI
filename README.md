# Medical-AI

医生端 **AI 草稿审核**研究平台（V3：`FastAPI` + `Next.js 14`，中文界面）。本分支问卷与行为记录已对齐 **问卷 7.0（PDF）** 中的变量编码词。

## 功能概览

- 前端：Next.js 14
- 后端：FastAPI + SQLAlchemy（async）+ Alembic
- 数据库：PostgreSQL（Docker）或本地 SQLite
- 研究流程：知情同意 → **前测（5 题 `pre_*`）** → 练习案例 → 正式案例 → **后测（Likert + 注意力题）** → 完成码
- 管理端：汇总、整库 / ZIP / 单表导出、LLM 总结接口

### 实验条件

- **guardrail（实验组）**：案例页展示护栏区（AI 总结、AI 风险提示等）。
- **plain（对照组）**：不展示护栏区，仅患者消息、病历摘要与 AI 草稿。
- 条件在创建会话时随机分配。

### 问卷 7.0（与 PDF 编码词一致）

| 阶段 | 说明 |
|------|------|
| 前测 | `backend/data/pre_survey.json` 与前端 `preSurveyConfig.ts`；答案写入 `participants` 表字段 **`pre_specialty`、`pre_training_level`、`pre_years_post_residency`、`pre_weekly_msg_volume`、`pre_ai_drafting_familiarity`**（与 PDF 蛇形编码一致）。 |
| 案例内嵌量表 | `case_decision_confidence`、`case_draft_helpfulness` → 表 **`case_surveys`** 同名列。 |
| 处理方式与原因 | 四选一动作仍用内部枚举 `selected_action`（与金标 `gold_action` 比对）；**PDF 第三节** 对应列 **`case_action_choice`（1–4）**、**`log_final_action`**（与 PDF 表格一致的类别中文，如「直接发送」）、**`case_action_reason`**（JSON：`code` + 可选 `text`）。 |
| 后测 | `post_surveys.payload` 为 Pydantic 校验后的对象，键名与 `backend/data/post_survey.json` 中各题 `id` 一致（如 `attn_post_1` 等）。 |

### 后台自动记录（PDF 第五节）

- 原始 UI 事件仍写入 **`ui_events`**（`/api/ui-event`）。
- 每次提交案例决策时，**`actions.client_stats`** 中**仅**保留与 PDF 第五节一致的 **`log_*`** 键（秒级时长用 `log_case_review_time`、`log_time_to_first_action` 等，**不再**使用 `_sec` 后缀）；由前端上报的原始字段（如 `timeToFirstClickMs`）在服务端用于计算后**不落库**。
- **`derived_*`（派生指标）与 `code_*`（人工编码）** 按 PDF 设计由**离线分析或人工编码**完成，本仓库不在数据库中写入这些派生/编码列。

### 案例页（医生端）要点

- **原样发送**：选择该项时需勾选核对确认后方可继续（界面文案「原样发送」；**`log_final_action`** 存 PDF 用语「直接发送」）。
- **病历摘要**：可展开 / 收起；**案例编号与进度**；草稿区滚动/停留等行为参与 `log_scroll_dwell_draft` 等汇总。
- **会话关联**：`POST /api/case/open` 返回 `casePresentationId`，用于 `ui_events` 与单次审题绑定。

### 数据导出

在后端 `.env` 配置 **`ADMIN_TOKEN`**。管理员可调用 `GET /api/admin/export/...`（详见 OpenAPI `/docs`）。

- **`actions` / `participants` / `case_surveys` 等 CSV**：与问卷相关的列名采用 **蛇形命名**，与数据库列及 PDF 编码词对齐（例如 `pre_specialty`、`case_action_choice`、`client_stats`）。
- 前端 `/admin?token=<ADMIN_TOKEN>` 提供下载入口。更多说明见 **`backend/README.md`**。

### 端到端数据覆盖自检（可选）

```bash
cd backend && .venv/bin/python -m app.scripts.full_export_scope_demo
```

## LLM（DeepSeek）

- 案例接口 `/api/case/{id}` 可调用 LLM 生成 `aiDraft`；不可用时回退种子数据。

## 本地运行（Docker）

1. 根目录准备 `.env`（可从 `.env.example` 复制）
2. `docker compose up -d --build`
3. 访问：前端 `http://localhost:3000`，健康检查 `http://localhost:8000/healthz`

## 数据库迁移

```bash
cd backend && alembic upgrade head
```

若从旧库升级，请按顺序应用包含 **`5f0e1d2c3b4a_pdf_column_names_participant_action`** 在内的全部迁移。

## 开发备注

- 勿提交含真实密钥的 `.env`
- 修改 `Dockerfile` 或依赖后建议 `docker compose up -d --build`
