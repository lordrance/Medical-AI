# Medical-AI

AI 草稿审核研究平台（V2 FastAPI + Next.js）。

## 功能概览

- 前端：Next.js 14（中文界面）
- 后端：FastAPI + SQLAlchemy + Alembic
- 数据库：PostgreSQL（Docker）
- 研究流程：知情同意 -> 前测 -> 练习案例 -> 正式案例 -> 后测 -> 完成码
- 管理端：汇总、导出、LLM 总结接口

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
