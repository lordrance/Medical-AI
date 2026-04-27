# 项目提示词 V2：医生端 AI 草稿审核模拟平台（中国本地化 + 前后端分离）

> 这份文档是给 AI 编程助手（或后续接手开发的同学）使用的"主提示词"。
> 来源：原 PDF《04_给开发学生的超详细开发手册_医生端AI草稿审核模拟平台_V3.pdf》+ V2 五点新需求。
> V1 实现见 `docs/PROJECT_PROMPT.md` / `docs/PROJECT_PLAN.md`（保留作 baseline）。

---

## 0. V2 相对 V1 的核心变化（5 点新需求）

1. **本地化为中文**：使用对象是**中国医生**，所以：
   - 全站 UI 文本中文化
   - 知情同意书、前后测问卷题目按中国医疗体系本地化（专科分类、培训层级、年资、消息平台名称、AI 工具品牌等）
   - 所有 case 的 patient message / chart snapshot / AI draft / guardrail 文本都改为中文，并贴近中国门诊/在线问诊的真实表达
2. **前后端分离 + FastAPI 后端**：
   - 后端：Python 3.11 + FastAPI + SQLAlchemy + Alembic + Pydantic v2
   - 前端：Next.js 14 + React + TypeScript + Tailwind + shadcn/ui
   - 通过 OpenAPI schema + 自动生成 TS client 保证类型同步
3. **预留 DeepSeek（或任意 LLM）API 接入位**：
   - 当前主实验仍使用**预先冻结**的 AI draft（保实验内部效度）
   - 但要建立 **`LLMProvider` 抽象层**，方便：
     - 管理员侧"一键为 case 重新生成 AI 草稿"（仍需 PI 审核冻结后才上线）
     - 实验后**自动总结每位医生的行为画像**（自然语言报告）
     - 未来 Paper 2 的 `mode_live_explanation` 模式
   - 通过环境变量 `LLM_PROVIDER=deepseek|disabled` 控制是否启用
4. **UI 美化**：
   - 引入设计规范（色彩 / 字体 / 间距 / 组件）
   - 用 shadcn/ui + lucide 图标
   - 提供 light/dark mode（默认 light）
   - 关键交互（4 个动作按钮、guardrail panel、likert）做精细化处理
5. **未来优化路线图**：详见本文档第 14 节

---

## 1. 你的角色（Role）

你是一名全栈工程师，负责把一个 HCI 实验平台从 V1（Next.js 单体）演进到 V2（FastAPI + Next.js 前后端分离 + 中文 + LLM 接入位 + UI 美化）。

---

## 2. 项目本质（必须先记住）

- **不是**：让医生和 AI 自由聊天的产品；不是真实临床部署。
- **是**：一个**脚本化、可控、可记录行为日志**的研究平台。
- **核心研究问题**：当中国医生审核 AI 草稿时，不同界面设计（Plain vs Guardrail）会不会改变其监督行为、错误纠正、验证、信任与责任判断。
- 主实验**保持冻结内容**，LLM 仅用于：
  - case 内容预生成（PI 审核后冻结）
  - 实验后行为画像/混淆矩阵的自然语言总结
  - 未来 live explanation 模式（Paper 2 扩展）

---

## 3. 必须交付的功能（Definition of Done）

### 3.1 实验前台（医生看到的）
- 完整中文流程：欢迎页 → 知情同意 → 前测问卷 → 练习案例 → 8 个正式案例 → 后测问卷 → 完成页
- 两种界面条件：**普通版（Plain）** 与 **加护栏版（Guardrail）**
- 4 种动作中文化：**直接发送 / 编辑后发送 / 弃用并重写 / 升级处理**
- 中文 case 内容（patient message / chart / AI draft / guardrail 文本）
- 总时长 28–32 分钟，硬上限 35 分钟

### 3.2 后端（FastAPI）
- 完整 REST API（OpenAPI schema 自动生成，挂载在 `/docs`）
- 数据库表 8 张（与 V1 等价：participants / sessions / case_presentations / actions / case_surveys / post_surveys / ui_events，外加 cases / order_templates 内容表）
- LLM provider 抽象层 + DeepSeek 适配器
- 管理员端鉴权 + CSV/JSON 导出 + 混淆矩阵 + 打分量表 + 自然语言总结

### 3.3 前端（Next.js）
- 中文 UI（含错误提示、加载态、空态）
- shadcn/ui 组件库 + 自定义主题
- 响应式（桌面优先；手机/平板可读但不强求）
- 自动从后端 OpenAPI 生成的 TS client（`pnpm gen:api`）

### 3.4 管理员后台
- 中文化的 `/admin/export` 页面
- 混淆矩阵中文动作标签 + 4 套打分指标说明
- "用 LLM 生成本次实验总结"按钮（仅在 `LLM_PROVIDER` 启用时可见）

---

## 4. 用户流程（中文）

| 步骤 | 页面 | 时长 | 内容 |
| --- | --- | --- | --- |
| 1 | 欢迎页/知情同意 | 1–2 分钟 | 说明这是脚本化研究、不收集任何真实病例信息 |
| 2 | 前测问卷 | 3–4 分钟 | 专科、培训层级、年资、每周线上问诊量、AI 使用经验、AI 熟悉度 |
| 3 | 练习案例 | 1–2 分钟 | 熟悉界面、4 种动作、3 道课后小题 |
| 4 | 8 个正式案例 | 18–22 分钟 | 每个案例审核决策 + 3 道 case-level 量表 |
| 5 | 后测问卷 | 6–8 分钟 | 信任 / 透明度 / 工作流契合度 / 责任 / 过度依赖担忧 |
| 6 | 结束页 | <1 分钟 | 致谢 + 完成码（可贴回招募问卷） |

---

## 5. 中国本地化要点

### 5.1 专科分类（前测题）
- 内科（心血管 / 呼吸 / 消化 / 内分泌 / 肾内 / 神经 / 血液 / 风湿免疫 / 感染）
- 外科（普外 / 骨科 / 神外 / 胸外 / 泌尿 / 心外 / 整形）
- 妇产科 / 儿科 / 急诊医学 / 全科医学 / 重症医学 / 麻醉
- 影像 / 检验 / 病理 / 中医 / 中西医结合
- 其他（请注明）

### 5.2 培训层级
- 医学生（本/硕/博）
- 规培住院医师（一阶段 / 二阶段）
- 主治医师
- 副主任医师
- 主任医师

### 5.3 每周线上问诊/患者消息量
- 0 / 1–10 条 / 11–25 条 / 26–50 条 / 51–100 条 / 100 条以上

### 5.4 AI 使用经验
- 从未使用 / 偶尔使用 / 每月使用 / 每周使用 / 每天使用

### 5.5 AI 工具品牌（多选）
- DeepSeek / 文心一言 / 通义千问 / 智谱清言 / 讯飞星火 / Kimi / 豆包 / ChatGPT / 其他海外模型

### 5.6 案例文本中文化原则
- 患者表达要符合中国普通患者的口语化（"医生，我从昨天开始..."、"我担心是不是..."、"要不要去医院呀？"）
- 用药使用国内常见品名（如 metformin 写"二甲双胍"，lisinopril 写"赖诺普利"）
- chart snapshot 字段：年龄、过敏史、当前用药、既往病史、最近检查、下次随访
- 升级动作文案改为：**"建议立即就诊 / 电话回访患者 / 建议急诊就医 / 其他升级处理"**

### 5.7 同意书重点（中文版）
- 强调"本研究不涉及真实病例和病人信息"
- 强调"您的回答将被脱敏存储，仅用于学术研究"
- 强调"您可以随时关闭页面退出研究"
- 提供研究负责人/伦理委员会联系方式占位符

---

## 6. 技术架构（V2）

```
┌──────────────────────┐         ┌──────────────────────┐
│   Frontend (Next.js) │ ──────► │  Backend (FastAPI)   │
│   + shadcn/ui        │  HTTP   │  + SQLAlchemy        │
│   + i18n (zh-CN)     │ ◄────── │  + Pydantic v2       │
└──────────────────────┘         └──────────┬───────────┘
                                            │
                                  ┌─────────┴────────┐
                                  │                  │
                         ┌────────▼─────┐   ┌────────▼──────┐
                         │  PostgreSQL  │   │  LLM Provider │
                         │  (or SQLite) │   │  (DeepSeek)   │
                         └──────────────┘   └───────────────┘
```

### 6.1 仓库结构

```
medical-ai-review/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                  # 路由
│   │   ├── core/                 # 配置 / 鉴权 / 日志
│   │   ├── db/                   # SQLAlchemy 模型 + session
│   │   ├── schemas/              # Pydantic schemas
│   │   ├── services/             # 业务（randomization / analysis / export）
│   │   └── llm/                  # LLM provider 抽象 + 适配器
│   ├── data/                     # 内容数据层（中文 cases）
│   ├── alembic/                  # DB migrations
│   ├── pyproject.toml
│   └── tests/
├── frontend/                     # Next.js 前端
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/                  # api client / i18n / utils
│   │   └── styles/
│   ├── package.json
│   └── tailwind.config.ts
├── docs/
│   ├── PROJECT_PROMPT_V2.md      # 本文件
│   ├── PROJECT_PLAN_V2.md        # 详细方案
│   └── PI_SOP.md                 # （V1 已有，V2 中文化）
├── docker-compose.yml            # 一键启动 backend + db + frontend
└── README.md
```

---

## 7. LLM 接入位（关键）

### 7.1 为什么要抽象

- 主实验**仍使用冻结内容**，否则破坏内部效度
- 但研究 / 运维仍需要 LLM：
  - 准备 case 时的初稿生成（PI 审核冻结后才上线）
  - 实验后给每个参与者生成"行为画像总结"（中文叙述）
  - Paper 2 的 live explanation 模式
- 因此用 `LLMProvider` 接口屏蔽底层
- 默认 `LLM_PROVIDER=disabled`，所有 LLM 入口在 UI 上**隐藏**

### 7.2 接口契约

```python
class LLMProvider(Protocol):
    name: str
    async def generate(self, *, system: str, user: str,
                       max_tokens: int = 1024,
                       temperature: float = 0.3) -> LLMResponse:
        ...
    async def health(self) -> bool: ...
```

### 7.3 适配器

- `DisabledProvider` —— 主实验默认；任何调用都返回 503 + 提示文案
- `DeepseekProvider` —— 通过 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL`（OpenAI 兼容协议）
- 预留 `OpenAIProvider`、`MoonshotProvider` 接口位

### 7.4 三个用法入口（仅管理员可见）

1. **`POST /api/admin/llm/case-draft`**：输入 patient message + chart snapshot，返回建议 AI 草稿。**不会**自动写入实验数据；PI 审核后通过 `data/cases.json` 冻结。
2. **`POST /api/admin/llm/participant-summary?participantId=...`**：基于该参与者的 actions / case_surveys / post_survey 自动生成行为画像（中文叙述）。
3. **`POST /api/admin/llm/cohort-summary`**：基于全部完成参与者的统计数据（混淆矩阵 + per-case + per-participant）生成中文总结报告。

### 7.5 安全约束

- LLM 接口**只接受管理员 token**
- 所有 LLM 调用必须落库（`llm_calls` 表：模型 / 输入 / 输出 / token 数 / 耗时 / 调用人 / 时间）
- 严禁把任何 PHI 喂给 LLM（已经天然成立，因为我们没有 PHI）
- 提供 dry-run 模式（返回模拟数据），便于无 API key 的开发

---

## 8. UI 美化要点

### 8.1 设计 Token

| Token | 值 |
| --- | --- |
| 主色 | `#0F766E`（深青绿，医疗领域中性可信感） |
| 强调色 | `#F59E0B`（琥珀，用于 guardrail 警示） |
| 错误色 | `#DC2626` |
| 成功色 | `#16A34A` |
| 字体 | 正文 `system-ui, "PingFang SC", "Microsoft YaHei", sans-serif`；等宽 `JetBrains Mono` |
| 圆角 | 8px / 12px |
| 阴影 | 极轻 `shadow-sm`，避免拟物 |
| 间距基础 | 4px 倍数 |

### 8.2 关键组件

- **进度条**：`Case 3 / 8` + 顶部细线进度
- **4 个动作按钮**：图标 + 中文 + 英文小字（提高识别速度），选中时主色填充
- **Guardrail 面板**：琥珀色边框 + 折叠箭头，每条事实/checklist 都用图标标记
- **量表（Likert 1–7）**：分段按钮，未选灰色，选中主色 + 阴影；左右两端中文锚点
- **编辑框**：自动高度，字数实时统计，placeholder 中文提示

### 8.3 布局

- 居中容器最大宽度 880px，避免一行过长影响阅读
- 案例页采用纵向单列流式布局：进度 → 患者消息 → 病历卡片 → AI 草稿 → 护栏面板 → 动作 → 编辑框 → 提交
- 每个 section 卡片化，section 之间留 24px 间距

### 8.4 微交互

- 路由切换淡入（150ms）
- 选中动作按钮时 200ms scale 反馈
- 提交按钮加载态用 spinner + 禁用态
- 字数统计与编辑距离提示（边输边算）

---

## 9. 数据收集（与 V1 一致 + 新增）

V1 的 5 层数据全部保留（participant / case / action / ui_event / case_survey / post_survey）。

**V2 新增**：
- `llm_calls`：所有 LLM 调用日志
- `Action.client_stats_json` 中新增 `language: "zh-CN"` 字段
- `Participant` 中 `specialty` / `training_level` 改为中国本地枚举
- `cohort_summaries`：管理员生成的总结报告归档

---

## 10. 随机化（与 V1 一致）

- Condition 50/50 随机；可启用 block randomization（每 4 人保 2:2）
- 4 套顺序模板，硬约束：defective 不连续 ≥3 / 高风险不全后半段 / 低风险准确不全前半段

---

## 11. 4 种动作（中文化）

| 英文 ID | 中文 UI 文案 | 文本框行为 |
| --- | --- | --- |
| `send_as_is` | **直接发送** | 不出现 |
| `edit_then_send` | **编辑后发送** | 出现，预填 AI 草稿 |
| `discard_and_rewrite` | **弃用并重写** | 出现，预填空白 |
| `escalate` | **升级处理** | 不出现，弹出升级类型下拉（立即就诊 / 电话回访 / 建议急诊 / 其他） |

---

## 12. 8 个正式案例（中文化原则）

保留 V1 的 8 个案例**结构与研究目的不变**，仅做中文化：

| Case | 主题（中文） | 风险 | 是否 defective | 主要 defect / 目的 | Gold Action |
| --- | --- | --- | --- | --- | --- |
| 01 | 服用赖诺普利后唇肿/声音变化 | 高 | 是 | 紧急程度被低估 / 错误安抚 | 升级处理 |
| 02 | 劳力性胸闷 | 高 | 否 | 准确升级 | 直接发送 / 轻微编辑 |
| 03 | 长途飞行后单侧小腿肿痛 | 高 | 是 | 关键风险遗漏 / 过早确认 | 升级处理 / 大改 |
| 04 | 轻度排尿灼热，无发热 | 低 | 否 | 常规分流 + red flag | 直接发送 / 轻微编辑 |
| 05 | 青霉素过敏却被建议阿莫西林 | 中高 | 是 | 事实幻觉 / chart grounding 错误 | 弃用并重写 / 大改 |
| 06 | 新用二甲双胍后胃肠道不适 | 低 | 否 | 常见副作用 + 安全网 | 直接发送 / 轻微编辑 |
| 07 | 服用布洛芬后黑便 + 站立头晕 | 高 | 否 | 准确升级 | 直接发送 / 轻微编辑 |
| 08 | 新发头痛但 AI 引用了不存在的 chart 信息 | 中低 | 是 | 推理缺陷 / 编造依据 | 编辑后发送 / 弃用并重写 |

具体文本由 `backend/data/cases.json` 提供。

---

## 13. 量表与问卷（中文化）

### 13.1 case 后 3 题（1–7 量表）
1. 我认为这条最终回复现在可以安全发送给患者。
2. 我对刚才的判断有信心。
3. AI 提供的草稿在本案例中是有帮助的。

锚点：1 = 非常不同意，7 = 非常同意

### 13.2 后测问卷（5 个 block，中文）
- **信任**（trust）
- **透明度 / 可解释性**（transparency）
- **工作流契合 / 负担**（workflow fit / burden）
- **责任 / 边界**（accountability）
- **过度依赖担忧**（overreliance concern）
- 开放题：你最希望平台增加什么功能；其他建议

---

## 14. 未来优化路线图（你问的第 5 点）

为了支撑论文与高质量数据采集，建议依次推进：

### 14.1 数据完整性 & 质量
1. **注意力检测题**（attention check）：嵌入 1 道明显题（"为研究目的请选 5"），过滤敷衍样本
2. **响应时间异常检测**：自动标记 case 时长 < 阈值 / >> p95 的样本
3. **完成性强校验**：序列号 + 时间戳防止伪造
4. **顺序模板更智能的随机化**：6 套或 8 套，进一步降低 carry-over effect
5. **block randomization** 保 condition 平衡
6. **服务端事件去重**：防同一 sessionId 重复创建

### 14.2 实验设计扩展
1. **Paper 2 live explanation 模式**：调 LLM 实时生成解释，记录展开次数与停留时长
2. **多种 guardrail 子条件**：仅 facts / 仅 risk / 仅 checklist / 全开 → 拆解哪一个组件最有效
3. **被试内设计支持**：每位医生看 4 个 plain + 4 个 guardrail（latin square 配置）
4. **难度级别标签**：按 case 复杂度分层抽样
5. **眼动 / 鼠标轨迹采集**（可选，用 rrweb 录屏前端）

### 14.3 数据采集深度
1. **细粒度编辑日志**：每次按键 + 节流后的 diff snapshot（重建医生编辑轨迹）
2. **panel 展开 / 折叠 / 滚动到底部**事件
3. **回退行为**：医生选了动作又改 → 关键 indecision 信号
4. **每个 checklist item 的勾选先后顺序**

### 14.4 招募与依从
1. **招募问卷整合**：内置邀请码 → 完成码绑定，自动对账
2. **微信扫码 / 短信验证完成**（可选）
3. **激励机制**：完成码 + 红包 / 积分 / 学时（接入第三方）
4. **多设备记录**：UA / 屏幕分辨率 / 网络 RTT

### 14.5 内容运营
1. **管理员侧 case 草稿生成**（DeepSeek 调用），PI 审核后冻结
2. **case 版本管理**：每次内容修改打版本号，追溯每位参与者看到的是哪一版
3. **多语言扩展**：留好 i18n 框架，未来可加英文/繁体

### 14.6 分析与发布
1. **自动报告**：管理员一键生成中文实验报告（混淆矩阵 + 四个核心 outcome + 关键图表 + LLM 总结）
2. **R/Python 分析模板**：仓库内放 `analysis/` 目录，含 mixed-effects model / SEM 示例
3. **可重现实验包**：导出 sealed dataset + 分析脚本 + 复现说明
4. **预注册 hash**：实验启动前对设计 + 假设 + 分析计划做哈希，防止 HARKing

### 14.7 部署与运维
1. **Docker compose 一键启动**：backend + frontend + postgres
2. **CI/CD**：GitHub Actions 跑 lint / type-check / pytest / smoke
3. **监控**：sentry 错误追踪 + uptime 告警
4. **备份**：每日 pg_dump + 异地存档
5. **HTTPS + WAF**：防止刷接口
6. **限流**：基于 sessionId 的 token bucket

### 14.8 合规
1. **IRB / 伦理委员会**模板（中文）
2. **数据脱敏导出**：`participant_id` 哈希一次再发给合作者
3. **数据主权**：服务部署在国内（推荐：阿里云 / 腾讯云 上海/北京区）
4. **个保法合规**：明确告知数据用途、保存期、销毁机制

---

## 15. 给 AI 助手的写代码风格约束

1. **单一真相**：内容来自 `backend/data/cases.json`；前端绝不硬编码
2. **类型同步**：FastAPI 暴露 OpenAPI → 前端 `pnpm gen:api` 生成 TS 客户端
3. **服务端时间戳为唯一真相**
4. **所有 LLM 调用走 `LLMProvider` 抽象**，禁止前端直接连第三方
5. **Prompt 集中管理**：`backend/app/llm/prompts/` 下每个用途一个 `.md` + Python loader
6. **可恢复**：刷新后能恢复到当前 step
7. **管理员页面 token 保护**：`X-Admin-Token` header 或 `?token=...`
8. **日志写失败不阻塞 UI**
9. **i18n key**：UI 文本走 i18n 字典，不直接写在组件里（即便目前只支持 zh-CN，先把架子搭好）

---

## 16. 第一步要做什么

1. 先读 `docs/PROJECT_PROMPT_V2.md`（本文件）和 `docs/PROJECT_PLAN_V2.md`（详细方案）
2. 创建 `backend/` 与 `frontend/` 子目录骨架
3. FastAPI 跑通 `GET /healthz`，OpenAPI 在 `/docs` 可访问
4. 把 V1 的 `data/*.json` 复制到 `backend/data/`，并按本文件第 5 节做中文化（先做 cases.json + 量表，再做案例正文）
5. 按 PROJECT_PLAN_V2 的 Phase 顺序推进

---

**最后一句**：你不是在做一个"聪明的中文医疗机器人"，而是在做"一个能让中国研究者严格控制材料、让中国医生用熟悉的语言完成真实审核任务、并把每一步行为留下来"的 HCI 实验平台。LLM 是辅助工具，不是核心产品。
