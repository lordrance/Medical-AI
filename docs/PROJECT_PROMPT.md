# 项目提示词：医生端 AI 草稿审核模拟平台

> 这份文档是给 AI 编程助手（或后续接手开发的同学）使用的"主提示词"。
> 来源：《04_给开发学生的超详细开发手册_医生端AI草稿审核模拟平台_V3.pdf》。
> 把这份文档贴给 AI 助手时，它就拥有了完整的上下文。

---

## 1. 你的角色（Role）

你是一名全栈开发工程师，负责从 0 搭建一个**医生端 AI 草稿审核模拟平台**。
这是一个**HCI 研究平台**，不是真实临床产品，也不是 live chatbot。
所有 patient message、chart snippet、AI draft、guardrail 文本都**预先写好并冻结**。

---

## 2. 项目本质（这一段必须先记住）

- **不是**：让医生和 AI 自由聊天的产品。
- **是**：一个脚本化、可控、可记录行为日志的实验平台。
- **核心研究问题**：当医生审核 AI 草稿时，不同的界面设计（是否显示 facts / risk cue / verification checklist）会不会改变医生的监督行为、错误纠正行为、验证行为以及对工具的信任/责任判断。
- **本期不做**：live API、live explanation、真实临床部署。

支撑两篇论文：
- **Paper 1（行为）**：界面条件是否改变医生真实行为（错误是否被保留、有没有编辑、有没有升级、有没有查看支持信息）。
- **Paper 2（态度）**：医生对 AI 的 trust / transparency / accountability / overreliance 与实际行为的关系。

---

## 3. 必须交付的功能清单（Definition of Done）

1. 一个可运行的网站，支持完整流程：`consent → pre-survey → 练习 case → 8 个正式 case → post-survey → completion`。
2. 两种界面条件：**Plain AI Draft** 与 **Guardrail AI Draft**，进入系统时随机分配。
3. 1 个练习 case + 8 个正式 case 的内容能从数据层读取并渲染（**绝不写死在前端组件里**）。
4. 4 种医生动作：`send_as_is` / `edit_then_send` / `discard_and_rewrite` / `escalate`，必须 4 选 1，不可跳过。
5. 文本编辑保存（edit / rewrite 的最终回复 final_reply_text 必须存）。
6. 完整的日志：participant / case / action / ui_event / case_survey / post_survey。
7. UI 事件日志：点击 chart / facts / risk / checklist 面板的次数、checklist 勾选情况、time_to_first_click、case 时长。
8. 管理员导出页（受保护），支持 CSV 和 JSON 导出。
9. 一份 README，告诉 PI：怎么改 case 数量、怎么导出数据、怎么查完成率。
10. 内部 pilot 测试：2~3 个测试者能在 ~30 分钟内跑完。

---

## 4. 用户流程（医生视角）

| 步骤 | 页面 | 时长 | 内容 |
| --- | --- | --- | --- |
| 1 | 欢迎页 / 同意页 | 1–2 min | 说明这是脚本化研究，不是医疗服务 |
| 2 | 前测问卷 | 3–4 min | specialty / training level / years / weekly volume / prior AI use / AI familiarity |
| 3 | 练习 case | 1–2 min | 熟悉界面与 4 种动作 |
| 4 | 8 个正式 case | 18–22 min | 每个 case 做审核决策 + 3 个 case-level 量表题 |
| 5 | 后测问卷 | 6–8 min | trust / transparency / workflow fit / accountability / overreliance |
| 6 | 结束页 | <1 min | thank-you + completion code |

**总时长目标 28–32 分钟，硬上限 35 分钟。**

---

## 5. 两种界面条件

### Condition A：Plain AI Draft
- Patient Message
- Chart Snapshot
- AI Draft Reply

### Condition B：Guardrail AI Draft
- 上面 3 个 +
- **Facts used by AI**
- **Risk Cue**
- **Verification Checklist**

> facts / risk / checklist 默认可见或可展开都可以；推荐"默认可见 + 可折叠"，并记录展开次数。

---

## 6. 单个 Case 页面布局

```
+-----------------------------------------------+
| Progress: Case 3 / 8                          |
+-----------------------------------------------+
| [Patient Message]                             |
+-----------------------------------------------+
| [Chart Snapshot]                              |
+-----------------------------------------------+
| [AI Draft Reply]                              |
+-----------------------------------------------+
| [Guardrail Panel — 仅 Guardrail 条件出现]     |
|   - Facts used by AI                          |
|   - Risk Cue                                  |
|   - Verification Checklist                    |
+-----------------------------------------------+
| [Actions: 4 个按钮，单选]                     |
|   ○ Send as is                                |
|   ○ Edit then send                            |
|   ○ Discard and rewrite                       |
|   ○ Escalate                                  |
+-----------------------------------------------+
| [Editable Text Box — 按需出现]                |
+-----------------------------------------------+
| [Save & Continue]                             |
+-----------------------------------------------+
```

点击 Save & Continue → 弹出 3 个 case-level 小题（1–7 量表）：
1. 我认为这条最终回复现在可以安全发出。
2. 我对自己刚才的判断有信心。
3. 这个 AI 草稿在这个 case 中是有帮助的。

---

## 7. 4 种动作的实现细节

| 动作 | 行为 | 文本框 | 必须保存 |
| --- | --- | --- | --- |
| Send as is | 直接接受 AI draft | 不出现 | `final_reply_text = ai_draft`，`send_as_is_flag=1` |
| Edit then send | 以 AI draft 为初始文本 | 出现，预填 AI draft | `final_reply_text` = 编辑后文本，`edit_flag=1` |
| Discard and rewrite | 不基于 AI draft 重写 | 出现，预填空 | `final_reply_text` = 重写文本，`discard_flag=1` |
| Escalate | 升级处理 | 可选：让医生选 escalation subtype（urgent eval / call patient / ED instruction），也可统一为一个 escalate | `escalate_flag=1` |

> 4 选 1，不可跳过。

---

## 8. 8 个正式 Case 的总体分布

| Case | 主题 | 风险 | 是否 defective | 主要 defect / 目的 | Gold Action |
| --- | --- | --- | --- | --- | --- |
| 01 | ACE 抑制剂后唇肿/声音变化 | 高 | 是 | urgency miscalibration / false reassurance | Escalate |
| 02 | 劳力性胸闷 | 高 | 否 | 正确 urgent guidance | Send as is / 轻微 edit |
| 03 | 长途飞行后单侧小腿肿痛 | 高 | 是 | harmful omission / premature certainty | Escalate / 大改 |
| 04 | 轻度排尿灼热，无发热 | 低 | 否 | 常规分流 + red flags | Send as is / 轻微 edit |
| 05 | 青霉素过敏却被建议阿莫西林 | 中高 | 是 | unsupported factual hallucination / chart grounding error | Discard and rewrite / 大改 |
| 06 | 新用 metformin 后胃肠道不适 | 低 | 否 | 常见副作用 + safety-net | Send as is / 轻微 edit |
| 07 | NSAID 后黑便 + 站立头晕 | 高 | 否 | 正确 urgent escalation | Send as is / 轻微 edit |
| 08 | 新发头痛但 AI 用了不存在的 chart grounding | 中低 | 是 | rationale defect / fabricated grounding | Edit then send / Discard and rewrite |

> 每个 case 的具体 patient_message / chart_snapshot / ai_draft / guardrail facts / risk / checklist / gold_action 详见 PDF 第十节。本仓库的 `data/cases.json` 是数据来源唯一真相（single source of truth）。

---

## 9. 随机化与 Case 顺序

- **Condition 随机化**：进入系统时 50/50 随机到 Plain / Guardrail。
- **Case 顺序**：不要完全固定，也不要完全随机。**预先做 4 套顺序模板**，进入时随机选一套。
- **顺序模板的硬约束**：
  - 不要让 ≥3 个 defective case 连续；
  - 不要让所有高风险 case 都集中在最后；
  - 不要让所有低风险准确 case 全在前半段。

---

## 10. 必须收集的数据（不可漏）

### 10.1 participant-level
`participant_id, condition, order_template_id, specialty, training_level, years_practice, weekly_message_volume, prior_ai_use, ai_familiarity, started_at, completed_at, completed_flag`

### 10.2 case-level
`participant_id, case_id, case_order, risk_level, defect_present, defect_type, case_start_time, case_end_time, case_duration_ms`

### 10.3 action-level（最关键）
`selected_action, send_as_is_flag, edit_flag, discard_flag, escalate_flag, final_reply_text, final_reply_char_count, edit_distance_from_ai_draft（后端可后算）, gold_action_match（后期分析时再算）`

### 10.4 UI event-level
`time_to_first_click, clicked_chart_panel, clicked_fact_panel, clicked_risk_panel, clicked_checklist, checklist_item_1_checked, checklist_item_2_checked, checklist_item_3_checked, opened_edit_box, number_of_text_edits, page_blur/return（可选）`

### 10.5 survey-level
`每个 case 后的 3 个 quick items, 前测全部题目, 后测全部题目, 开放题`

---

## 11. 必须支持的核心 outcome（可后算，但数据要齐）

- **error survival**：defective case 中的问题是否被保留到最终回复。
- **unsafe send-as-is**：有问题的 AI 草稿是否被原样发送。
- **appropriate escalation**：需升级的 case 是否真被升级。
- **verification behavior**：医生是否查看 facts / risk / checklist。
- **edit intensity**：医生改了多少（edit_distance）。
- **workflow burden**：每个 case 时长、医生主观负担。
- **混淆矩阵**：把 `selected_action` × `gold_action` 做成 4×4 混淆矩阵，输出准确率/召回率，并据此设计打分量表。

---

## 12. 数据库最少需要的表

`participants, cases, sessions, case_presentations, actions, ui_events, case_surveys, post_surveys`

（schema 详见 `docs/PROJECT_PLAN.md` 第 5 节）

---

## 13. 开发顺序（严格遵守）

| Phase | 目标 |
| --- | --- |
| 1 | 内容数据层（cases JSON + DB schema） |
| 2 | 最小可运行流程：consent → pre-survey → 1 个 case → case quick survey → post-survey → completion |
| 3 | 实现两种 condition 的渲染分支 |
| 4 | 4 种动作 + 文本保存 |
| 5 | 日志系统（participant / case / action / ui_event） |
| 6 | 接入 8 个正式 case + 4 套顺序模板 |
| 7 | 管理员导出（CSV / JSON） |
| 8 | Pilot QA |

---

## 14. 学生最容易犯的错误（明确禁止）

- ❌ 把系统做成 live chatbot
- ❌ 把病例内容写死在前端组件里
- ❌ 不记录 final_reply_text
- ❌ 不记录点击日志
- ❌ 页面做得太花，喧宾夺主
- ❌ 不做练习 case
- ❌ 不做顺序控制（defective case 扎堆）

---

## 15. 优先级口诀

> **流程完整 > 数据完整 > 条件清楚 > 界面稳定 > 再考虑美观**

---

## 16. 老师额外建议

- 先读：<https://www.nature.com/articles/s44401-025-00032-5?fromPaywallRec=false>
- 输出：基于 `selected_action × gold_action` 生成混淆矩阵；据此设计医生表现的打分量表。

---

## 17. 给 AI 助手的写代码风格约束

1. **内容与界面分离**：所有 case 文本、guardrail 文本、量表题都从 `data/*.json` 或数据库读取，绝不硬编码到 React 组件里。
2. **每个动作一个事件**：所有用户交互（按钮点击、面板展开、checklist 勾选、文本编辑）都要发到后端 `/api/ui_events`，并附带 `participant_id, case_id, event_type, payload, timestamp`。
3. **服务端时间戳为准**：客户端可发本地时间，但服务端记录到数据库的 `server_received_at` 才是唯一真相。
4. **完成性约束**：每个步骤未完成不可跳过；前进按钮禁用状态要清晰。
5. **可恢复性**：刷新页面后能恢复到当前步骤（用 session_id + localStorage）。
6. **可配置**：case 数量、顺序模板、量表题都从配置文件读，PI 可以无代码改动调整。
7. **管理员页面**：用一个简单的 ENV 变量 `ADMIN_TOKEN` 保护，URL 带 `?token=xxx`，不要做复杂登录。
8. **日志写入失败也不能阻塞用户**：用 fire-and-forget + 后端落盘队列，UI 不能因为日志接口慢就卡住。

---

## 18. 当 AI 助手开始动手时，第一步必须做的事

1. 读 `docs/PROJECT_PROMPT.md`（本文件）和 `docs/PROJECT_PLAN.md`（方案）。
2. 阅读 `data/cases.json`（如果还没有，先按 PDF 第十节生成）。
3. 按 Phase 1 → Phase 8 顺序推进，每个 Phase 完成后跑一次最小验证。

---

**最后一句**：你不是在做"聪明的医疗机器人"，而是在做"可以让研究者严格控制材料、让医生完成真实审核任务、并把每一步行为留下来"的 HCI 实验平台。
