# 项目方案：医生端 AI 草稿审核模拟平台

> 配套提示词：`docs/PROJECT_PROMPT.md`
> 本文档面向开发者，解释技术选型、目录结构、数据模型、接口设计、分阶段任务清单。

---

## 1. 设计原则

1. **内容与界面分离**：所有 case 文本、量表题、顺序模板都放在 `data/` 下的 JSON / SQL 种子文件里。
2. **数据完整 > UI 美观**：先保证日志和导出，再优化界面。
3. **服务端为唯一真相**：所有时间戳、随机分配、最终文本都以后端记录为准。
4. **简单部署**：单个仓库 + 单个 Postgres（pilot 用 SQLite 也行）+ Vercel/自建 VPS。
5. **可配置**：case 数量、顺序模板、量表题、ADMIN_TOKEN 都通过配置/环境变量调整。

---

## 2. 技术栈

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端 | **Next.js 14（App Router）+ React 18 + TypeScript** | 同仓库前后端，路由清晰；服务端组件减少 boilerplate |
| UI | **Tailwind CSS + shadcn/ui** | 快速、风格中性、不喧宾夺主 |
| 后端 | **Next.js Route Handlers（`app/api/*`）** | 不引入额外服务 |
| 数据库 | **PostgreSQL**（开发期可 SQLite） | 长字段、JSON、并发都稳；导出方便 |
| ORM | **Prisma** | schema-first，迁移与 seed 体验好 |
| 表单 | **react-hook-form + zod** | 类型安全、校验集中 |
| 状态 | **Zustand**（实验流程状态机） | 比 Redux 轻 |
| 部署 | Vercel 或 Docker | 灵活 |
| 包管理 | pnpm | 速度与磁盘占用都更友好 |

> 如果学生更熟 Vue / FastAPI，可替换为：FastAPI + Postgres + Vue3 + Vite。但**目录与数据契约保持一致**。

---

## 3. 目录结构

```
medical-ai-review/
├── docs/
│   ├── PROJECT_PROMPT.md        # 主提示词
│   ├── PROJECT_PLAN.md          # 本文件
│   └── README.md                # 给 PI 的使用说明（Phase 7 完成）
├── data/
│   ├── cases.json               # 1 个练习 case + 8 个正式 case（内容真相）
│   ├── order_templates.json     # 4 套 case 顺序模板
│   ├── pre_survey.json          # 前测题目结构
│   ├── post_survey.json         # 后测题目结构
│   └── case_quick_survey.json   # 每个 case 后的 3 个量表题
├── prisma/
│   ├── schema.prisma            # 8 张表
│   ├── migrations/
│   └── seed.ts                  # 把 data/*.json 灌入数据库
├── src/
│   ├── app/
│   │   ├── (study)/             # 实验流程组（共享布局）
│   │   │   ├── consent/page.tsx
│   │   │   ├── pre-survey/page.tsx
│   │   │   ├── practice/page.tsx
│   │   │   ├── case/[order]/page.tsx
│   │   │   ├── post-survey/page.tsx
│   │   │   └── completion/page.tsx
│   │   ├── admin/
│   │   │   └── export/page.tsx  # 受 ADMIN_TOKEN 保护
│   │   ├── api/
│   │   │   ├── session/route.ts        # POST 新建 session（含随机分配）
│   │   │   ├── pre-survey/route.ts
│   │   │   ├── case/[id]/route.ts      # GET 单个 case 内容
│   │   │   ├── action/route.ts         # POST 提交审核动作
│   │   │   ├── case-survey/route.ts    # POST case 后 3 题
│   │   │   ├── ui-event/route.ts       # POST UI 事件
│   │   │   ├── post-survey/route.ts
│   │   │   └── admin/export/route.ts   # GET CSV / JSON
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── case/                # CasePage、PatientMessage、ChartSnapshot、AIDraft、GuardrailPanel、ActionButtons、EditBox
│   │   ├── survey/              # 量表题组件
│   │   └── ui/                  # shadcn 组件
│   ├── lib/
│   │   ├── prisma.ts
│   │   ├── randomization.ts     # condition + order template 随机分配
│   │   ├── session.ts           # 客户端状态（Zustand）
│   │   ├── logger.ts            # UI 事件采集封装
│   │   └── export.ts            # CSV/JSON 导出工具
│   └── config/
│       └── env.ts               # 环境变量校验（zod）
├── tests/                       # （后续阶段补）
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── .env.example
└── README.md
```

---

## 4. 数据模型（Prisma schema 概览）

| 表 | 关键字段 | 备注 |
| --- | --- | --- |
| `Participant` | id, condition, orderTemplateId, demographics（specialty/training/years/volume/priorAiUse/aiFamiliarity）, startedAt, completedAt, completedFlag | 一行 = 一个参与者 |
| `Case` | id（如 `case_01`）, isPractice, riskLevel, defectPresent, defectType, patientMessage, chartSnapshot(JSON), aiDraft, factsUsed(string[]), riskCue, checklist(string[]), goldAction | 内容真相 |
| `Session` | id, participantId, startedAt, endedAt, status | 一次实验会话 |
| `CasePresentation` | id, sessionId, caseId, orderIndex, startedAt, endedAt, durationMs | 谁在第几个看到了哪个 case |
| `Action` | id, casePresentationId, selectedAction, sendAsIsFlag, editFlag, discardFlag, escalateFlag, escalateSubtype?, finalReplyText, finalReplyCharCount, editDistance(int?), serverReceivedAt | 4 选 1 |
| `UiEvent` | id, sessionId, casePresentationId?, eventType, payload(JSON), clientTs, serverTs | 全量点击日志 |
| `CaseSurvey` | id, casePresentationId, item1, item2, item3 | 三个 1–7 量表 |
| `PostSurvey` | id, sessionId, payload(JSON) | 整体后测，按 block 存 JSON |

完整 `schema.prisma` 在 Phase 1 落地。

---

## 5. 核心 API 契约（草案）

```
POST /api/session
  body: { demographics? }   # demographics 也可放在 pre-survey
  resp: { sessionId, participantId, condition: 'plain'|'guardrail',
          orderTemplateId, caseOrder: ['case_xx', ...] }

POST /api/pre-survey
  body: { sessionId, answers }
  resp: { ok }

GET  /api/case/:caseId?sessionId=...
  resp: { case: {...} }     # 已根据 condition 决定是否返回 facts/risk/checklist

POST /api/action
  body: { sessionId, caseId, selectedAction, finalReplyText, escalateSubtype?,
          startedAt, endedAt, clientStats: {...} }
  resp: { ok, casePresentationId }

POST /api/case-survey
  body: { casePresentationId, item1, item2, item3 }
  resp: { ok }

POST /api/ui-event
  body: { sessionId, casePresentationId?, eventType, payload, clientTs }
  resp: { ok }

POST /api/post-survey
  body: { sessionId, payload }
  resp: { ok, completionCode }

GET  /api/admin/export?token=...&format=csv|json&table=...
  resp: 文件下载
```

---

## 6. 状态机（前端流程）

```
INIT → CONSENT → PRE_SURVEY → PRACTICE
     → CASE_1 → CASE_QUICK_SURVEY_1
     → ... → CASE_8 → CASE_QUICK_SURVEY_8
     → POST_SURVEY → COMPLETION
```

- 状态保存在 `Zustand` + `localStorage`，刷新可恢复。
- 每个状态推进都触发后端记录。

---

## 7. 随机化算法

```ts
// lib/randomization.ts
function assignCondition(): 'plain' | 'guardrail' {
  // 50/50 简单随机；为防止极端不平衡，可用 block randomization（每 4 人一组保证 2:2）
}

function pickOrderTemplate(): number {
  // 4 套模板，等概率
}
```

4 套顺序模板放在 `data/order_templates.json`，每套都满足三条硬约束（详见提示词第 9 节）。

---

## 8. UI 事件采集策略

- 在 `lib/logger.ts` 暴露 `logEvent(type, payload)`。
- 内部用 `navigator.sendBeacon` 或 `fetch(..., {keepalive: true})`，**fire-and-forget**。
- 关键事件：
  - `case_view_start` / `case_view_end`
  - `panel_clicked`（payload: chart / facts / risk / checklist）
  - `checklist_item_toggled`（payload: index, checked）
  - `action_button_selected`
  - `edit_box_opened` / `edit_box_keystroke`（节流到每秒一次）
  - `save_continue_clicked`
  - `page_blur` / `page_focus`
- 所有事件以 `serverTs` 为准；客户端 `clientTs` 仅供参考。

---

## 9. 管理员导出

- `/admin/export?token=xxx`
- 列表展示 8 张表，每张可导出 CSV 或 JSON。
- 顶部展示完成率：`completed / total`。
- 顶部展示**混淆矩阵**：`selected_action × gold_action`（来自 case 真相 + action 表）。
- 提供"打分量表"预览：每个 participant 在 8 个 case 上的命中数 / 准确率 / 错误存活率。

---

## 10. 安全与合规

- 不收集 PHI；同意页明确告知"虚构 case，不是医疗服务"。
- `ADMIN_TOKEN` 仅放 `.env`，不进 git。
- 数据库连接字符串放 `.env`；`.env.example` 提供模板。
- 提供 `participant_id` 假名化，不绑定真实身份。

---

## 11. 分阶段任务清单（与 PROJECT_PROMPT 第 13 节对齐）

### Phase 1 — 内容数据层 ✅ 本轮先做这个
- [ ] `data/cases.json`（练习 case + 8 个正式 case，按 PDF 第十节）
- [ ] `data/order_templates.json`（4 套顺序）
- [ ] `data/pre_survey.json` / `data/post_survey.json` / `data/case_quick_survey.json`
- [ ] `prisma/schema.prisma`（8 张表）
- [ ] `prisma/seed.ts`（读取 JSON 灌库）

### Phase 2 — Next.js 脚手架 + 最小流程
- [ ] `pnpm create next-app` + Tailwind + shadcn/ui
- [ ] `consent → pre-survey → 1 个 case → case quick survey → post-survey → completion`
- [ ] `lib/session.ts` 状态机
- [ ] 路由保护：未完成 consent 不能进 case 页

### Phase 3 — 两种 condition
- [ ] `randomization.ts` + `/api/session`
- [ ] CasePage 根据 condition 决定是否渲染 GuardrailPanel
- [ ] 后端按 condition 过滤返回字段（防止前端嗅探）

### Phase 4 — 4 种动作
- [ ] ActionButtons 组件
- [ ] EditBox 组件（按 action 决定预填）
- [ ] `/api/action`：保存 final_reply_text，计算 char_count；edit_distance 后端后算
- [ ] 校验：必须 4 选 1

### Phase 5 — 日志系统
- [ ] `lib/logger.ts`（fire-and-forget）
- [ ] `/api/ui-event`
- [ ] CasePage 内埋点：panel_clicked / checklist_toggle / opened_edit_box / time_to_first_click
- [ ] case_start_time / case_end_time / case_duration_ms

### Phase 6 — 8 个 case + 顺序模板
- [ ] `/api/session` 返回 caseOrder
- [ ] `case/[order]` 路由按 caseOrder 推进
- [ ] 验证 4 套模板都满足约束

### Phase 7 — 管理员导出 + README
- [ ] `/api/admin/export`
- [ ] `/admin/export` 页面（token 保护）
- [ ] 混淆矩阵 + 打分量表预览
- [ ] `README.md`：怎么改 case、怎么导出、怎么看完成率

### Phase 8 — Pilot QA
- [ ] 2~3 人内测，时长 ≤35 min
- [ ] 数据导出抽样检查

---

## 12. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 前端嗅探 guardrail 内容 | 后端按 condition 过滤；guardrail 字段在 plain 条件下不返回 |
| 日志接口慢导致 UI 卡 | sendBeacon + 后端落盘队列 |
| 医生中途退出 | 状态可恢复；记录 completedFlag=false 的样本 |
| case 内容拼写错误 | seed 后跑一个校验脚本核对字段非空 |
| 顺序模板违反约束 | 在 seed 阶段写校验逻辑，违规则报错 |

---

## 13. 完成标准（Definition of Done）

与 PROJECT_PROMPT 第 3 节一致：
- 流程完整 ✓
- 两种 condition ✓
- 8 个 case ✓
- 4 种动作 ✓
- final_reply_text 保存 ✓
- 全量日志可导出 ✓
- 30 分钟内能跑完 ✓
- README 可让 PI 上手 ✓

---

**下一步**：按 Phase 1 开始动手 —— 先把 `data/cases.json` 等内容数据层落下来。
