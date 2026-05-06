# Backend · FastAPI

医生端 AI 草稿审核模拟平台的后端，使用 FastAPI + SQLAlchemy（async）+ Pydantic v2。

## 本地开发（Phase 0 当前能跑通的部分）

```bash
cd backend

# 1) 创建虚拟环境（推荐 uv）
python -m venv .venv && source .venv/bin/activate

# 2) 安装依赖（含 dev）
pip install -e ".[dev]"

# 3) 复制 .env
cp .env.example .env

# 4) 启动开发服务器
uvicorn app.main:app --reload --port 8000

# 浏览器访问：
#   - http://localhost:8000/healthz
#   - http://localhost:8000/docs        ← OpenAPI Swagger UI
#   - http://localhost:8000/openapi.json
```

## 数据导出（管理员）

- 在 `.env` 设置 `ADMIN_TOKEN`（生产环境请使用长随机串）。
- **整库 SQL**：`GET /api/admin/export/full-database`（Header `X-Admin-Token` 或 `?token=`）  
  - SQLite：返回 `iterdump` 文本，可本地还原。  
  - PostgreSQL：需服务器安装 `pg_dump`，否则返回 503。
- **多表 ZIP（CSV）**：`GET /api/admin/export/bundle`  
  - 默认打包全部研究相关表 + `summary.csv`。  
  - 节选：`/api/admin/export/bundle?tables=actions,ui_events`  
- **单表**：`GET /api/admin/export?table=actions&format=csv`（见 OpenAPI `/docs`）。

前端管理页 `admin?token=...` 提供整库与 ZIP 的下载入口。

## V3 近期变更摘要（与本分支相关）

- **案例交互**：原样发送前核对勾选；病历可折叠；案例编号与进度；行为打点与 `POST /api/case/open`；plain 组不展示护栏区。
- **管理员导出**：整库 SQL（`/api/admin/export/full-database`）、多表 ZIP（`/api/admin/export/bundle`）、单表扩展至 `cases`、`order_templates`、`llm_calls`、`cohort_summaries`。
- **演示脚本**：`python -m app.scripts.showcase_export_demo`、`python -m app.scripts.full_export_scope_demo`（可选）。

## 测试

```bash
pytest -q
```

## 数据相关命令

```bash
# 校验内容数据完整性 + 顺序模板硬约束
python -m app.scripts.validate_data

# 灌入 cases + order_templates 到数据库（幂等 upsert）
python -m app.scripts.seed

# Alembic
alembic upgrade head            # 应用所有 migration
alembic revision --autogenerate -m "your message"   # 生成新 migration
```

本地 DeepSeek + `/api/case` 完整路径与可视化脚本说明见 **`docs/LOCAL_INTEGRATION_TEST.md`**（脚本本身放在 `backend/tools/`，不纳入版本库）。

## 后续 Phase

- Phase 2：完整业务 API（session / case / action / surveys / ui-event / admin）
- Phase 4：LLM provider 抽象 + DeepSeek 适配器 + 管理员 LLM 入口
