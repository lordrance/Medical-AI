# 本地集成测试：DeepSeek + `risk_tip` / `case_draft` + `/api/case`

说明如何在**本机**验证真实 LLM 与 FastAPI 串联。**请勿**把一次性测试脚本、可视化脚本提交到 GitHub；仓库已通过 `.gitignore` 忽略目录 `backend/tools/`。

---

## 前置

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env：LLM_PROVIDER=deepseek，LLM_DRY_RUN=false，DEEPSEEK_API_KEY=...

alembic upgrade head
python -m app.scripts.seed
```

---

## 方式 A：临时进程 + curl（HTTP）

**终端 1**

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**终端 2**

```bash
# 创建会话，记下 sessionId；若需护栏组可多试几次 POST 直到 condition 为 guardrail
curl -s -X POST http://127.0.0.1:8000/api/session

SESSION="<上一步返回的 sessionId>"

# 练习案例：非 defect，aiDraft 由 case_draft 提示词 + DeepSeek 生成
curl -s "http://127.0.0.1:8000/api/case/case_practice?sessionId=$SESSION" | jq '.case.aiDraft[:200]'

# 正式缺陷案例 case_01（guardrail）：riskCue 为 risk_tip + DeepSeek；aiDraft 仍为种子缺陷稿
curl -s "http://127.0.0.1:8000/api/case/case_01?sessionId=$SESSION" | jq '.case | {aiDraftPreview: .aiDraft[:120], riskCuePreview: .guardrail.riskCue[:120]}'
```

期望：`case_practice` 的 `aiDraft` 为较长中文；`guardrail` 存在且 `riskCue` 非空。`case_01` 的 `aiDraft` 仍含种子中的错误表述片段（项目逻辑：defect 案例固定种子稿）。

---

## 方式 B：AsyncClient 脚本（不落库 HTTP）

在本地自行创建 **`backend/tools/integration_llm_case_api.py`**（该路径已被 gitignore），内容可用 Cursor 根据以下条件生成：

- `AsyncClient` + `ASGITransport(app=app)`
- 先 `POST /api/session` 直到 `guardrail`，再请求 `case_practice`、`case_01`
- 断言：`DEEPSEEK_API_KEY` 存在、`LLM_PROVIDER=deepseek`、`LLM_DRY_RUN=false`
- 校验 defect 案例 `case_01` 的 `aiDraft` 仍包含种子片段（与 `cases.json` 一致）

运行：

```bash
cd backend
export LLM_PROVIDER=deepseek LLM_DRY_RUN=false
export DEEPSEEK_API_KEY=...
python tools/integration_llm_case_api.py
```

---

## 数据可视化（本地）

将可视化脚本放在 **`backend/tools/visualize_study_data.py`**（同上，勿提交），依赖 `matplotlib`，读当前 `DATABASE_URL` 库表生成 `backend/out/charts/*.png`。

---

**CI 说明**：仓库内 `pytest` 仍默认 `LLM_PROVIDER=disabled`，不调用外部 API。
