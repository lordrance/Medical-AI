# Medical-AI

医生端 **AI 草稿审核** HCI 研究平台（V3：`FastAPI` + `Next.js 14`，中文界面）。
本仓库的问卷、行为记录与字段命名已对齐 **问卷 7.0 PDF** 中的变量编码词。

> 研究问题：在医生审核 AI 起草的患者回复时，**护栏区 UI**（AI 总结、风险提示、检查清单）
> 是否改善决策质量、影响认知负担与责任感知。

## 1. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Next.js 14（App Router）+ TypeScript + Tailwind |
| 后端 | FastAPI + SQLAlchemy 2.x（async）+ Alembic |
| 数据库 | PostgreSQL（Docker）/ SQLite（本地或 CI 临时库） |
| LLM | DeepSeek（可配置）；`disabled` / `dry_run` 兜底 |
| 部署 | `docker-compose.yml` / `docker-compose.prod.yml` |

## 2. 实验流程

```
知情同意 → 前测（5 题 pre_*） → 练习案例 → 8 个正式案例 → 后测（Likert + 注意力 + 3 道开放题） → 完成码
```

### 实验条件（创建会话时随机分配）

- **`guardrail`（实验组）**：案例页展示护栏区——`factsUsed`（事实使用列表）、`riskCue`（AI 风险提示，LLM 生成或回退种子文案）、`checklist`（核查项）。
- **`plain`（对照组）**：只显示患者消息、病历摘要、AI 草稿。

## 3. 问卷 7.0 字段映射

| 阶段 | 数据落表 | 说明 |
|---|---|---|
| 前测 | `participants.pre_specialty` / `pre_training_level` / `pre_years_post_residency` / `pre_weekly_msg_volume` / `pre_ai_drafting_familiarity` | 配置见 [backend/data/pre_survey.json](backend/data/pre_survey.json) + [frontend preSurveyConfig.ts](frontend/src/lib/forms/preSurveyConfig.ts) |
| 案例内嵌量表 | `case_surveys.case_decision_confidence` / `case_draft_helpfulness` | Likert 1–5 |
| 处理动作 | `actions.case_action_choice`（1–4，PDF 编码）+ `log_final_action`（PDF 中文用语，如「直接发送」）+ `case_action_reason`（JSON：`code` + 可选 `text`） | 四种动作：`send_as_is` / `edit_then_send` / `discard_and_rewrite` / `escalate`；金标比对字段 `actions.selected_action` |
| 后测 | `post_surveys.payload`（Pydantic `PostSurveyV7Payload` 强校验） | 题目键名与 [backend/data/post_survey.json](backend/data/post_survey.json) 的 `id` 一致 |

### 后测开放题（3 道，V3 改版）

后测末尾 3 道开放题已对齐"未来场景"主题，键名与题意贴近：

| ID | 主题 |
|---|---|
| `post_qual_l1_ehr_pain_ai_substitution` | EHR 日常使用痛点 + AI 可替代/协助的环节 + 仍需医生本人完成的部分 |
| `post_qual_l2_human_ai_boundary` | Agentic AI 在医疗场景中可独立处理的任务边界 + 必须保留医生最终决策权的环节 |
| `post_qual_l3_system_transformation` | AI 大规模采用后医疗系统在组织、角色、医患关系层面的预期变化 |

## 4. 后台自动记录（PDF 第五节）

- **原始 UI 事件流**：`POST /api/ui-event` → 写入 `ui_events` 表（含语音输入起止、面板展开/收起、滚动等）。失败时静默丢弃但会写 `logger.warning`（fire-and-forget 语义保留）。
- **案例决策汇总指标**：每次提交 `POST /api/action` 时，服务端把前端原始字段（如 `timeToFirstClickMs`、`panelClickCounts`）计算为 PDF 编码词 **`log_*`** 字段后写入 `actions.client_stats`：
  - `log_case_review_time`、`log_time_to_first_action`（秒级浮点，**无 `_sec` 后缀**）
  - `log_send_as_is` / `log_edit_then_send` / `log_discard_rewrite` / `log_escalate`（互斥 0/1）
  - `log_edit_actions` / `log_source_panel_open` / `log_help_risk_panel` / `log_toggle_draft_source` / `log_verification_clicks`
  - `log_scroll_dwell_draft`（嵌套对象：`section_dwell_sec` / `max_depth_ratio` / `scroll_event_count`）
- **`derived_*`（派生指标）与 `code_*`（人工编码）** 不在数据库中，由离线分析或人工编码完成。

## 5. LLM 与审计

LLM 通过工厂模式选择 provider（`backend/app/llm/factory.py`），目前支持：

| Provider | 用途 |
|---|---|
| `deepseek` | 真实调用 DeepSeek Chat API |
| `dry_run` | 测试/演示用，返回固定文本 |
| `disabled` | 不可用，所有调用抛 `LLMUnavailable` 并触发回退到种子文案 |

### 审计完整性

**所有 LLM 调用**（含受试者使用过程中的 case_draft / risk_tip，以及 admin 端的 case_draft / participant_summary / cohort_summary）**成功和失败**都通过 [services/llm_audit.py](backend/app/services/llm_audit.py) 写入 `llm_calls` 表。研究人员可据此核对 token 用量、失败率与成本。

> **设计约束**：`defect_present=True` 的案例**不**调用 LLM 生成 `case_draft`——否则模型会"修正"种子草稿中故意保留的缺陷，破坏实验有效性。但 guardrail 组的 `risk_tip` 仍会调用（受 [test_defect_case_skips_case_draft_llm_call](backend/tests/test_llm.py) 保护）。

## 6. 数据导出

后端 `.env` 配置 **`ADMIN_TOKEN`** 后，管理员可调用：

| 端点 | 用途 |
|---|---|
| `GET /api/admin/export?table=<name>&format=csv\|json` | 单表导出 |
| `GET /api/admin/export/bundle?tables=...` | 多表 ZIP 打包（默认全量） |
| `GET /api/admin/export/full-database` | SQLite `iterdump` / Postgres `pg_dump` 整库 SQL |
| `GET /api/admin/summary` | 完成率 + 混淆矩阵 + per-case / per-participant 统计 |
| `POST /api/admin/llm/cohort-summary` | LLM 生成群体总结 → 同时写 `cohort_summaries` 表 |

支持表：`participants` / `sessions` / `case_presentations` / `actions` / `case_surveys` / `post_surveys` / `ui_events` / `cases` / `order_templates` / `llm_calls` / `cohort_summaries` / `summary`。

**字段命名约定**：
- 与问卷 PDF 直接对应的列（`pre_specialty`、`case_action_choice`、`client_stats` 等）使用 **蛇形命名**，对齐 PDF 编码词。
- DB metadata 列（`sessionId`、`caseId`、`payloadJson` 等）使用 **驼峰**。

前端 `/admin?token=<ADMIN_TOKEN>` 提供可视化下载入口。

### 端到端数据覆盖自检

```bash
cd backend && .venv/bin/python -m app.scripts.full_export_scope_demo
# 或：python -m app.scripts.showcase_export_demo
```

## 7. 本地运行

### Docker（推荐）

```bash
# 1. 准备 .env（从 .env.example 复制）
# 2. 启动
docker compose up -d --build
# 3. 访问：前端 http://localhost:3000，健康检查 http://localhost:8000/healthz
```

### 直接运行（不用 Docker）

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev   # http://localhost:3000
```

## 8. 数据库迁移

```bash
cd backend && alembic upgrade head
```

若从旧库升级，请按顺序应用所有 alembic 迁移（含 `5f0e1d2c3b4a_pdf_column_names_participant_action`）。

## 9. 测试与质量保证

```bash
cd backend && python -m pytest -q
# 全套：40 个测试，约 17 秒，覆盖率 ~61%
```

测试覆盖：

- **E2E 受试者全流程**（[test_e2e_flow.py](backend/tests/test_e2e_flow.py)）：会话创建 → 前测 → 案例打开（含 reuse 复用）→ 提交动作 → 后测 → 完成码。
- **模拟用户数据导出**（[test_simulated_user_export_flow.py](backend/tests/test_simulated_user_export_flow.py)）：模拟 8 个案例的完整行为流水（含语音事件、面板切换计数、checklist 勾选），然后断言 `participants` / `actions` / `case_surveys` / `post_surveys` / `ui_events` CSV 导出全部命中 marker 字符串。
- **LLM 审计回归**（[test_llm.py](backend/tests/test_llm.py)）：验证受试者侧 LLM 调用（成功 / 失败）和 admin 侧（`participant_summary` / `cohort_summary`）**所有错误路径**都写入 `llm_calls`。
- **PDF 字段持久化**（[test_pdf_persistence_qa.py](backend/tests/test_pdf_persistence_qa.py)）：核对 `case_action_choice` 1–4、`log_final_action` 中文用语、`case_action_reason` JSON 结构。
- **种子数据 + Schema 校验**（[test_data_validation.py](backend/tests/test_data_validation.py)、[test_seed.py](backend/tests/test_seed.py)）。

### CI（GitHub Actions）

变更 `backend/**` 或工作流文件时触发 [.github/workflows/backend-ci.yml](.github/workflows/backend-ci.yml)：
**同一套 `pytest` 先在临时 SQLite 上跑，再在 PostgreSQL 15 服务容器上跑**（与 `docker-compose` 的 `postgresql+asyncpg://…` 驱动一致）。

## 10. 开发备注

- 勿提交含真实密钥的 `.env`（已在 `.gitignore`）。
- 修改 `Dockerfile` 或依赖后建议 `docker compose up -d --build`。
- LLM 调用统一走 [services/llm_audit.py](backend/app/services/llm_audit.py)，新增 LLM 端点时务必调用 `record_llm_call`，**包含错误分支**——否则研究 token 用量审计会出现盲点。
- `defect_present=True` 案例的 `aiDraft` 是研究故意保留的缺陷文案，**不要让 LLM 重写**。
