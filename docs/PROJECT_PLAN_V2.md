# 项目方案 V2：医生端 AI 草稿审核模拟平台

> 配套提示词：`docs/PROJECT_PROMPT_V2.md`
> 本文档面向开发者，详细描述 V2 的技术架构、目录、API、数据库、迁移策略、分阶段任务清单。

---

## 1. 设计原则

1. **前后端分离**：后端只做数据 + 业务 + LLM；前端只做 UI + 交互。
2. **OpenAPI 驱动类型同步**：后端 schema 改了，前端 `pnpm gen:api` 自动跟进。
3. **内容与界面分离**：所有案例文本来自 `backend/data/*.json`，前端不硬编码。
4. **LLM 是可选模块**：默认禁用；启用时也只在管理员侧出现入口。
5. **i18n 优先**：所有 UI 文案走字典，目前仅 zh-CN，但留好 i18n 框架。
6. **可观测**：所有用户事件 + LLM 调用都落库。

---

## 2. 技术栈

### 2.1 后端

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.11 | LLM 生态、社区成熟 |
| Web 框架 | **FastAPI** | 自带 OpenAPI、Pydantic v2、async |
| ORM | **SQLAlchemy 2.0**（async） | 主流稳定 |
| Migration | **Alembic** | 与 SQLAlchemy 配套 |
| Schema | **Pydantic v2** | 与 FastAPI 深度集成 |
| 数据库 | **PostgreSQL 15+**（生产）/ **SQLite**（开发/pilot） | 按需切换；`DATABASE_URL` 一行改 |
| LLM HTTP | **httpx** + DeepSeek OpenAI 兼容协议 | 异步 |
| 鉴权 | 简单 admin token（环境变量）；如需扩展可上 OAuth | 小项目够用 |
| 测试 | **pytest** + **pytest-asyncio** | 标准 |
| 包管理 | **uv**（推荐）或 **pip + venv** | uv 速度快 |
| 进程 | **uvicorn**（开发）/ **gunicorn + uvicorn worker**（生产） | 标配 |

### 2.2 前端

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 框架 | **Next.js 14 App Router** + **React 18** + **TypeScript** | 与 V1 一致 |
| UI Kit | **shadcn/ui**（基于 Radix）+ **lucide-react** 图标 | 现代美观，可自定义 |
| 样式 | **Tailwind CSS 3** | 与 shadcn 配套 |
| 状态 | **Zustand** + persist | V1 已用，保持 |
| 表单 | **react-hook-form** + **zod** | 类型安全 |
| API 客户端 | **openapi-typescript** + 自定义 fetch wrapper | OpenAPI → TS |
| i18n | **next-intl** 或自建轻量字典 | 先用自建字典即可 |
| 包管理 | **pnpm** | 速度快 |

### 2.3 部署

| | 选型 |
| --- | --- |
| 后端 | Docker + uvicorn 镜像 |
| 前端 | Docker + Next.js standalone 模式 |
| 数据库 | Docker postgres：15-alpine |
| 一键启动 | `docker-compose.yml` 拉起 backend + frontend + db |
| 反代 | Nginx（生产）；开发用 Next.js 自带 |
| 监控 | Sentry（可选） |

---

## 3. 仓库结构

```
medical-ai-review/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── core/
│   │   │   ├── config.py              # Settings (pydantic-settings)
│   │   │   ├── security.py            # admin token 校验
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── base.py                # Base 类
│   │   │   ├── session.py             # async session
│   │   │   └── models.py              # SQLAlchemy 模型
│   │   ├── schemas/
│   │   │   ├── case.py
│   │   │   ├── action.py
│   │   │   ├── survey.py
│   │   │   ├── session.py
│   │   │   └── llm.py
│   │   ├── api/
│   │   │   ├── deps.py                # 依赖注入：DB session / admin / 当前 session
│   │   │   ├── healthz.py
│   │   │   ├── session.py             # POST /api/session
│   │   │   ├── case.py                # GET /api/case/{id}
│   │   │   ├── action.py              # POST /api/action
│   │   │   ├── survey.py              # POST /api/pre-survey, /api/post-survey
│   │   │   ├── ui_event.py            # POST /api/ui-event
│   │   │   └── admin/
│   │   │       ├── export.py          # GET /api/admin/export
│   │   │       ├── summary.py         # GET /api/admin/summary
│   │   │       └── llm.py             # POST /api/admin/llm/...
│   │   ├── services/
│   │   │   ├── randomization.py       # condition + order template
│   │   │   ├── analysis.py            # 混淆矩阵 / per-case / per-participant
│   │   │   ├── export.py              # CSV / JSON
│   │   │   └── edit_distance.py       # Levenshtein
│   │   └── llm/
│   │       ├── base.py                # LLMProvider Protocol
│   │       ├── disabled.py            # DisabledProvider
│   │       ├── deepseek.py            # DeepseekProvider
│   │       ├── prompts/               # 各场景 prompt 模板
│   │       │   ├── case_draft.md
│   │       │   ├── participant_summary.md
│   │       │   └── cohort_summary.md
│   │       └── factory.py
│   ├── data/                          # 内容数据层（中文）
│   │   ├── cases.json
│   │   ├── order_templates.json
│   │   ├── pre_survey.json
│   │   ├── post_survey.json
│   │   └── case_quick_survey.json
│   ├── alembic/
│   ├── alembic.ini
│   ├── tests/
│   │   ├── test_session.py
│   │   ├── test_action.py
│   │   ├── test_admin_export.py
│   │   └── test_llm.py
│   ├── pyproject.toml
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── (study)/
│   │   │   │   ├── consent/page.tsx
│   │   │   │   ├── pre-survey/page.tsx
│   │   │   │   ├── practice/page.tsx
│   │   │   │   ├── case/[order]/page.tsx
│   │   │   │   ├── post-survey/page.tsx
│   │   │   │   └── completion/page.tsx
│   │   │   ├── admin/
│   │   │   │   └── page.tsx
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── ui/                    # shadcn 组件（生成）
│   │   │   ├── case/
│   │   │   │   ├── CasePage.tsx
│   │   │   │   ├── PatientMessage.tsx
│   │   │   │   ├── ChartSnapshot.tsx
│   │   │   │   ├── AIDraftReply.tsx
│   │   │   │   ├── GuardrailPanel.tsx
│   │   │   │   ├── ActionButtons.tsx
│   │   │   │   ├── EditBox.tsx
│   │   │   │   └── QuickSurvey.tsx
│   │   │   ├── survey/
│   │   │   │   └── Likert.tsx
│   │   │   └── layout/
│   │   │       ├── Header.tsx
│   │   │       └── ProgressBar.tsx
│   │   ├── lib/
│   │   │   ├── api/                   # 生成的 + 手写的 client
│   │   │   ├── i18n/
│   │   │   │   └── zh-CN.ts
│   │   │   ├── store.ts               # Zustand
│   │   │   ├── logger.ts
│   │   │   └── utils.ts
│   │   └── styles/
│   │       └── globals.css
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/
│   ├── PROJECT_PROMPT_V2.md
│   ├── PROJECT_PLAN_V2.md
│   ├── PI_SOP.md
│   └── （V1 文档保留）
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 4. 数据库模型（SQLAlchemy）

| 表 | 字段（要点） | 备注 |
| --- | --- | --- |
| `participants` | id, condition, order_template_id, specialty, training_level, years_practice, weekly_message_volume, prior_ai_use, ai_familiarity, ai_brands_used (JSON), started_at, completed_at, completed_flag | specialty / training_level 用中国本地枚举字符串 |
| `sessions` | id, participant_id, status, started_at, ended_at | |
| `cases` | id, is_practice, risk_level, defect_present, defect_type, purpose, patient_message, chart_snapshot (JSON), ai_draft, facts_used (JSON), risk_cue, checklist (JSON), gold_action, gold_action_alternates (JSON), version | 新增 `version` |
| `order_templates` | id, order (JSON) | |
| `case_presentations` | id, session_id, case_id, order_index, started_at, ended_at, duration_ms | |
| `actions` | id, case_presentation_id, selected_action, *flags, escalate_subtype, final_reply_text, final_reply_char_count, edit_distance, client_stats (JSON), server_received_at | client_stats 含 zh-CN |
| `case_surveys` | id, case_presentation_id, safe_to_send, confidence_in_judgment, ai_draft_helpful | |
| `post_surveys` | id, participant_id, session_id, payload (JSON), server_received_at | |
| `ui_events` | id, session_id, case_presentation_id?, event_type, payload (JSON), client_ts, server_ts | |
| `llm_calls` | id, purpose (`case_draft / participant_summary / cohort_summary`), provider, model, prompt_text, response_text, prompt_tokens?, completion_tokens?, latency_ms, created_at, created_by_admin | 新表 |
| `cohort_summaries` | id, payload_json (含报告原文), created_at | 新表 |

---

## 5. 核心 API 契约（OpenAPI 自动生成）

```
GET  /healthz                              -> {ok: true}

POST /api/session                          # 不带 body
  resp: {sessionId, participantId, condition, orderTemplateId,
         caseOrder: [...], practiceCaseId}

POST /api/pre-survey
  body: {sessionId, answers: {...中国本地化字段}}
  resp: {ok: true}

GET  /api/case/{caseId}?sessionId=...
  resp: {case: {... 按 condition 过滤 ...}}

POST /api/action
  body: {sessionId, caseId, orderIndex, selectedAction, finalReplyText,
         escalateSubtype?, quickSurvey, timing, clientStats}
  resp: {ok, casePresentationId, editDistance}

POST /api/case-survey                      # action 与 survey 已合并到 /api/action
  （V2 取消独立接口；保留旧名 alias 以备测试）

POST /api/post-survey
  body: {sessionId, payload}
  resp: {ok, completionCode}

POST /api/ui-event
  body: {sessionId, casePresentationId?, eventType, payload, clientTs}
  resp: {ok: true}

# 管理员（需 X-Admin-Token）
GET  /api/admin/summary                    # JSON 摘要
GET  /api/admin/export?table=...&format=csv|json

POST /api/admin/llm/case-draft             # body: {patientMessage, chartSnapshot}
POST /api/admin/llm/participant-summary    # body: {participantId}
POST /api/admin/llm/cohort-summary         # body: {} -> 基于全部完成参与者
```

CORS：开发环境允许 `http://localhost:3000`；生产环境精确域名白名单。

---

## 6. LLM Provider 抽象

```python
# app/llm/base.py
from typing import Protocol
from pydantic import BaseModel

class LLMResponse(BaseModel):
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int

class LLMProvider(Protocol):
    name: str
    async def generate(self, *, system: str, user: str,
                       max_tokens: int = 1024,
                       temperature: float = 0.3) -> LLMResponse: ...
    async def health(self) -> bool: ...
```

工厂：

```python
# app/llm/factory.py
def get_provider() -> LLMProvider:
    name = settings.LLM_PROVIDER  # "deepseek" | "disabled"
    if name == "deepseek":
        return DeepseekProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.DEEPSEEK_MODEL,
        )
    return DisabledProvider()
```

每次调用都写 `llm_calls` 表，包含输入 / 输出 / 模型 / token / 耗时。

Prompts 位置：`app/llm/prompts/*.md`，加载器：

```python
def load_prompt(name: str) -> tuple[str, str]:
    """returns (system, user_template)"""
    ...
```

---

## 7. 前端 API 客户端

1. 后端启动后 OpenAPI 在 `/openapi.json`
2. 前端 `pnpm gen:api` → 调 `openapi-typescript` 生成 `frontend/src/lib/api/types.ts`
3. 手写 fetch wrapper（处理 baseURL / cookie / error / sendBeacon）

`frontend/src/lib/api/index.ts`：

```ts
import type { paths } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function api<P extends keyof paths, M extends keyof paths[P]>(
  path: P, method: M, init?: RequestInit
): Promise<...> { ... }
```

---

## 8. UI 美化方案

### 8.1 主题（Tailwind + shadcn theme）

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --primary: 173 80% 26%;            /* #0F766E 深青绿 */
  --primary-foreground: 0 0% 100%;
  --accent: 32 95% 50%;              /* #F59E0B 琥珀 */
  --destructive: 0 84% 60%;
  --success: 142 71% 45%;
  --muted: 210 16% 96%;
  --border: 220 13% 91%;
  --radius: 0.5rem;
}
```

### 8.2 关键组件实现思路

- **`<ActionButtons />`**：`grid grid-cols-2 gap-3`，每个按钮含 `lucide` 图标 + 中文 + 英文小字
  - `Send`：`Send` 图标
  - `Edit3`：编辑后发送
  - `RefreshCcw`：弃用并重写
  - `AlertTriangle`：升级处理
- **`<GuardrailPanel />`**：琥珀边框，`Accordion` 折叠展开（默认展开），每个子区有图标和"已查看"打钩
- **`<Likert />`**：`RadioGroup` + 7 个 segmented 按钮，左右锚点用 `text-muted-foreground` 极小字
- **`<ProgressBar />`**：顶部细线进度，`width = (current/total) * 100%`
- **`<EditBox />`**：`Textarea` + 字数实时统计 + 与 AI draft 的相似度提示

### 8.3 中文字体优化

```css
font-family:
  "PingFang SC",
  "Hiragino Sans GB",
  "Microsoft YaHei",
  "Helvetica Neue",
  Arial,
  sans-serif;
```

### 8.4 动效

- 路由切换：Next.js `View Transitions` 或自定义 `framer-motion`（可选）
- 选中按钮：`transition-all duration-150 ease-out`
- 加载态：`Skeleton` 组件

---

## 9. i18n 框架

`frontend/src/lib/i18n/zh-CN.ts`：

```ts
export const t = {
  consent: {
    title: "知情同意",
    body1: "您将审核若干虚构的患者消息以及 AI 起草的回复...",
    agree: "我已阅读上述内容，同意参与本研究",
    continue: "我同意 — 开始",
  },
  case: {
    progress: (i: number, n: number) => `案例 ${i} / ${n}`,
    patientMessage: "患者消息",
    chartSnapshot: "病历摘要",
    aiDraft: "AI 起草的回复",
    guardrail: "护栏面板",
    factsUsed: "AI 使用的事实",
    riskCue: "风险提示",
    checklist: "核查清单",
    actions: {
      send_as_is: "直接发送",
      edit_then_send: "编辑后发送",
      discard_and_rewrite: "弃用并重写",
      escalate: "升级处理",
    },
    saveAndContinue: "保存并继续",
  },
  // ...
};
```

未来加英文版只需 `en.ts`，再在 `Provider` 切换。

---

## 10. 迁移策略（V1 → V2）

| 项 | 处理 |
| --- | --- |
| V1 `src/`（Next.js 后端 + 前端） | 整体作废，但保留分支留档 |
| V1 `data/*.json` | 迁移到 `backend/data/*.json` 并中文化 |
| V1 `prisma/schema.prisma` | 转写成 SQLAlchemy 模型；Alembic 重新生成 migration |
| V1 `docs/PROJECT_PROMPT.md` / `PROJECT_PLAN.md` | 保留，作为历史参考 |
| V1 `scripts/` | 重写为 Python 版（`backend/scripts/validate_data.py / sanity_check.py / e2e_smoke.py`） |
| V1 PR #2 | 不 merge；新建 v2 PR |

---

## 11. 分阶段任务清单

### Phase 0 — 仓库结构 + FastAPI 骨架（本轮做）
- [ ] 新建 `backend/` 与 `frontend/` 子目录
- [ ] `backend/pyproject.toml`、FastAPI app factory、`/healthz`
- [ ] `docker-compose.yml`（postgres + backend；前端先不容器化）
- [ ] `backend/.env.example`
- [ ] 跑通 `uvicorn app.main:app --reload`，访问 `/docs` 可见 OpenAPI

### Phase 1 — 数据模型 + 内容中文化
- [ ] SQLAlchemy 模型（10 张表）+ Alembic 初始迁移
- [ ] `backend/data/*.json` 中文化（cases / order_templates / pre_survey / post_survey / case_quick_survey）
- [ ] `backend/scripts/validate_data.py` + `seed.py`
- [ ] 单测覆盖：模型创建、seed 流程

### Phase 2 — FastAPI 完整 API
- [ ] `/api/session`（含随机分配）
- [ ] `/api/case/{id}`（按 condition 过滤）
- [ ] `/api/pre-survey`、`/api/post-survey`
- [ ] `/api/action`（含 edit_distance 计算）
- [ ] `/api/ui-event`
- [ ] `/api/admin/summary`、`/api/admin/export`（CSV/JSON）
- [ ] CORS、admin token、单测覆盖

### Phase 3 — Next.js 前端中文化 + UI 美化
- [ ] 新前端项目初始化（shadcn/ui init）
- [ ] 设计 token + 主题
- [ ] i18n 字典 zh-CN
- [ ] 把 V1 的页面逐个用 shadcn 重做
- [ ] OpenAPI client 生成脚本

### Phase 4 — DeepSeek provider + 管理员侧 LLM 入口
- [ ] `LLMProvider` 抽象 + DisabledProvider + DeepseekProvider
- [ ] Prompt 模板 3 个（case_draft / participant_summary / cohort_summary）
- [ ] `/api/admin/llm/*` 三个接口
- [ ] `llm_calls` 表 + 写入逻辑
- [ ] dry-run 模式（无 API key 时返回模拟数据）
- [ ] 前端管理员页加按钮 + 弹窗显示总结

### Phase 5 — 案例文本中文化（最重要的内容工作）
- [ ] 8 个 case 的中文版（含患者消息、病历摘要、AI 草稿、guardrail）
- [ ] 量表题目中文化
- [ ] 同意书 + 完成页中文化
- [ ] PI / 临床合作者 review 通过

### Phase 6 — 管理员端中文化 + 混淆矩阵中文标签
- [ ] `/admin` 页面中文化
- [ ] 4 个动作列名用中文 + 英文小字
- [ ] 打分量表说明用中文
- [ ] 一键导出 / 一键 LLM 总结

### Phase 7 — 测试 + 部署
- [ ] pytest 后端单测
- [ ] Playwright 前端 E2E（可选）
- [ ] Dockerfile 双端
- [ ] docker-compose 一键启动
- [ ] 在 staging 环境跑一次 pilot

---

## 12. 风险与对策

| 风险 | 对策 |
| --- | --- |
| OpenAPI 改动后前后端类型不同步 | CI 步骤：先启 backend → `pnpm gen:api` → diff 判断 |
| LLM 调用费用超支 | `llm_calls` 表 + Grafana 看板；预算 ENV 上限触发熔断 |
| LLM 失败回退 | `DisabledProvider` 永远可用；前端按钮在禁用模式下灰显 |
| 中文 case 翻译不专业 | 必须临床医生 review；提供版本号 + 可回滚 |
| 前后端跨域 | 开发用 `next.config.mjs` rewrites 或 backend CORS；生产用 Nginx 反代同源 |
| Postgres 与 SQLite 行为差异 | 单测里都跑一遍；JSON 字段统一用 `JSON` 类型 |

---

## 13. 完成标准（DoD）

- [ ] backend `pytest` 全绿
- [ ] frontend `pnpm build` 通过
- [ ] OpenAPI 在 `/docs` 可访问
- [ ] 完整流程能跑通（中文）
- [ ] LLM 入口在 `LLM_PROVIDER=disabled` 时隐藏；启用时能成功调用
- [ ] 管理员导出 CSV/JSON 正常
- [ ] 混淆矩阵 + per-case + per-participant 都展示中文动作标签
- [ ] PI SOP 中文版交付

---

## 14. 下一步

按 Phase 0 → 1 → 2 → 3 顺序推进。每个 Phase 单独 commit，单独自检。
