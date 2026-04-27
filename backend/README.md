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

## 测试

```bash
pytest -q
```

## 后续 Phase

- Phase 1：SQLAlchemy 模型 + Alembic + 中文化数据 seed
- Phase 2：完整业务 API（session / case / action / surveys / ui-event）
- Phase 4：LLM provider 抽象 + DeepSeek 适配器 + 管理员 LLM 入口
