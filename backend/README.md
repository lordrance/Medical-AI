# Backend · FastAPI

医生端 AI 草稿审核模拟平台的后端（FastAPI + SQLAlchemy async + Pydantic v2）。

## 本地开发

```bash
cd backend

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- `http://localhost:8000/healthz`
- `http://localhost:8000/docs`（OpenAPI）

## 问卷 7.0 与数据库字段（与 PDF 编码词对齐）

### `participants`

| 列名 | 说明 |
|------|------|
| `pre_specialty` | 科室 |
| `pre_training_level` | 职称 / 培训阶段 |
| `pre_years_post_residency` | 规培后年限 |
| `pre_weekly_msg_volume` | 周消息量 |
| `pre_ai_drafting_familiarity` | AI 起草熟悉度（整数 Likert） |

前测提交：`POST /api/pre-survey`，请求体 `answers` 的键须为上述 `pre_*` 名称。

### `case_surveys`

| 列名 |
|------|
| `case_decision_confidence` |
| `case_draft_helpfulness` |

### `actions`（除既有 flags / `selected_action` 外）

| 列名 | 说明 |
|------|------|
| `case_action_choice` | 1–4，与 PDF 处理方式编码一致 |
| `log_final_action` | PDF 第三节类别文本（如「直接发送」「编辑后发送」…） |
| `case_action_reason` | JSON：`{"code": "<枚举>", "text": "<可选说明>"}` |
| `client_stats` | **仅**含 PDF 第五节 **`log_*`** 自动记录键（如 `log_case_review_time`、`log_verification_clicks`、`log_scroll_dwell_draft` 等）；**不含** `derived_*` / `code_*`（离线或人工完成） |

提交：`POST /api/action`，请求体仍使用驼峰 API 字段（如 `caseActionReasonCode`），服务端映射到上表列名与 `client_stats` 结构。

### `post_surveys`

`payload` 经 `PostSurveyV7Payload` 校验，键与 `data/post_survey.json` 中题目 `id` 一致。

## 数据导出（管理员）

在 `.env` 设置 `ADMIN_TOKEN`。

- 整库 SQL：`GET /api/admin/export/full-database`
- 多表 ZIP：`GET /api/admin/export/bundle`
- 单表 CSV/JSON：`GET /api/admin/export?table=…`

`actions`、`participants`、`case_surveys` 导出中与问卷相关的字段名与数据库列一致（蛇形）。

## 测试与数据脚本

```bash
pytest -q
python -m app.scripts.validate_data
python -m app.scripts.seed
```

演示导出：`python -m app.scripts.showcase_export_demo`、`python -m app.scripts.full_export_scope_demo`。

## Alembic

```bash
alembic upgrade head
alembic revision --autogenerate -m "your message"
```

问卷 7.0 结构迁移：`4c7d8e9f0a1b_questionnaire_v7_schema`；**PDF 列名与 `client_stats` 键名**对齐：`5f0e1d2c3b4a_pdf_column_names_participant_action`。

## 后续 Phase

- Phase 2：完整业务 API（session / case / action / surveys / ui-event / admin）
- Phase 4：LLM provider 抽象 + DeepSeek 适配器

本地 DeepSeek 联调说明见 **`docs/LOCAL_INTEGRATION_TEST.md`**（脚本在 `backend/tools/`，不纳入版本库）。
