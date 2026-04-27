# Medical-AI · 医生端 AI 草稿审核模拟平台

一个 HCI 实验平台，研究医生在审核 AI 起草的 patient-message 回复时，不同界面设计（Plain vs. Guardrail）会如何影响其行为。

> 完整背景与设计请见 [`docs/PROJECT_PROMPT.md`](docs/PROJECT_PROMPT.md) 与 [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)。

---

## 当前进度

| Phase | 内容 | 状态 |
| --- | --- | --- |
| 1 | 内容数据层（cases / orders / surveys） | ✅ |
| 2 | Next.js 脚手架 + 最小可运行流程 | ✅ |
| 3 | Plain / Guardrail 两种 condition 渲染 | ✅（随脚手架一起完成） |
| 4 | 4 种动作 + 文本编辑保存 | ✅（随脚手架一起完成） |
| 5 | 日志系统加固 | ⏳ 下一步 |
| 6 | 4 套顺序模板随机化 | ✅（随脚手架一起完成） |
| 7 | 管理员导出（CSV/JSON）+ 混淆矩阵 | ⏳ |
| 8 | Pilot QA | ⏳ |

> Phase 3/4/6 在 Phase 2 的最小流程中已经完整接通，但还会在后续 Phase 单独加强（例如 edit_distance 后算、checklist 展开次数、混淆矩阵导出等）。

---

## 技术栈

- **Next.js 14（App Router）+ React 18 + TypeScript**
- **Tailwind CSS**
- **Prisma ORM + SQLite**（开发期）
- **Zustand**（实验流程状态机）
- **Zod**（API 校验）

---

## 本地启动

```bash
# 1. 安装依赖
pnpm install

# 2. 复制环境变量
cp .env.example .env

# 3. 推送 schema 到 SQLite + 灌入 case 数据
pnpm db:push
pnpm db:seed

# 4. 启动开发服务
pnpm dev
# 访问 http://localhost:3000

# 5. 校验内容数据完整性（任何修改 data/*.json 后都跑一下）
pnpm validate-data
```

## 完整流程

医生在浏览器看到的步骤：

```
/ → /consent → /pre-survey → /practice
  → /case/0 → ... → /case/7
  → /post-survey → /completion
```

每一步：

- `/consent`：知情同意；点击 Continue 时通过 `POST /api/session` 创建参与者，**随机分配 condition（plain/guardrail）和 4 套顺序模板之一**。
- `/pre-survey`：背景问卷，写入 participant 表。
- `/practice`：练习 case，标记 isPractice=true，主分析时排除。
- `/case/[order]`：8 个正式 case；每个 case 完成后弹出 3 个量表题。
- `/post-survey`：5 个 block 的后测（trust / transparency / workflow / accountability / overreliance）。
- `/completion`：感谢 + completion code。

---

## 数据模型

| 表 | 作用 |
| --- | --- |
| `Case` | case 内容（patient message / chart snapshot / AI draft / guardrail / gold action） |
| `OrderTemplate` | 4 套 case 顺序模板 |
| `Participant` | 参与者（含 condition、demographics、完成标志） |
| `Session` | 一次实验会话 |
| `CasePresentation` | 谁在第几个看到了哪个 case，含起止时间和 durationMs |
| `Action` | 4 种动作 + final_reply_text + char_count |
| `CaseSurvey` | 每个 case 后的 3 个 1–7 量表 |
| `UiEvent` | 全量点击/展开/编辑日志 |
| `PostSurvey` | 整体后测，按 block 存 JSON |

完整 schema：`prisma/schema.prisma`。

---

## 修改 case / 顺序 / 题目

所有内容都是**数据驱动**，不修改任何 React 组件即可调整：

| 想做什么 | 改哪个文件 |
| --- | --- |
| 新增 / 修改 case 内容 | `data/cases.json` |
| 新增 / 修改 case 顺序模板 | `data/order_templates.json` |
| 新增 / 修改前测题 | `data/pre_survey.json` |
| 新增 / 修改后测题 | `data/post_survey.json` |
| 新增 / 修改 case 后 3 题 | `data/case_quick_survey.json` |

改完之后：

```bash
pnpm validate-data       # 校验完整性 + 顺序约束
pnpm db:reset            # 清库 + 重新灌入（仅开发期；正式实验勿用！）
```

---

## 项目结构

```
medical-ai-review/
├── docs/                 # 项目提示词 + 详细方案
├── data/                 # 内容数据层（cases / orders / surveys）
├── prisma/               # schema.prisma + seed.ts + dev.db
├── scripts/              # validate-data.mjs
├── src/
│   ├── app/              # Next.js App Router（页面 + API）
│   ├── components/case/  # CasePage、GuardrailPanel、Likert
│   └── lib/              # prisma / randomization / session-store / logger / types
├── tailwind.config.ts
└── next.config.mjs
```

---

## 设计要点（与 PDF 对齐）

- ✅ **不是 live chatbot**，所有 AI draft 与 guardrail 文本预先写好并冻结。
- ✅ **内容与界面分离**：所有 case 文本来自 `data/cases.json`，组件不硬编码任何医疗内容。
- ✅ **后端按 condition 过滤**：plain 条件下 `/api/case/*` **不返回** facts/risk/checklist，杜绝前端嗅探。
- ✅ **4 种动作必选其一**：未选不能 Save & Continue。
- ✅ **顺序模板硬约束**：`scripts/validate-data.mjs` 自动检查 defective 不连续 ≥3 / 高风险不全在后半段 / 低风险准确不全在前半段。
- ✅ **服务端时间戳为唯一真相**：`Action.serverReceivedAt`、`CasePresentation.startedAt/endedAt` 由后端记录。
- ✅ **可恢复**：刷新后通过 `localStorage` 恢复 step + caseIndex。

---

## 后续 Phase 计划

- **Phase 5**：补足 UI event 埋点，加 edit_distance 后算 job、checklist 展开次数、page_blur/return。
- **Phase 7**：`/admin/export?token=...` 受保护页面，导出 CSV/JSON，自动算 `selected_action × gold_action` 混淆矩阵。
- **Phase 8**：邀请 2–3 个内部测试者跑通整个流程，验证 ≤35 分钟可完成、所有日志都能正确导出。
