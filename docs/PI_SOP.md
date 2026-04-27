# PI 操作 SOP（Standard Operating Procedure）

> 给负责实验的研究者（PI / RA）使用的"开实验/管实验/收数据"完整手册。
> 你不需要懂代码就能照着做。

---

## 阶段 0 · 实验前准备（一次性）

### 0.1 让一位开发同学帮你部署

只需要：

- 一台能跑 Node.js 的服务器（或者直接本地电脑也行）
- Node.js ≥ 18 + pnpm
- 把代码 clone 下来，跑：

```bash
pnpm install
cp .env.example .env
# 编辑 .env，把 ADMIN_TOKEN 改成只有你知道的密钥
pnpm db:push && pnpm db:seed
pnpm build && pnpm start
```

服务跑起来后会有两个 URL：

- **参与者入口**：`https://你的域名/`
- **管理员后台**：`https://你的域名/admin/export?token=你的ADMIN_TOKEN`

> 把"参与者入口"发给医生，**不要**把"管理员后台"链接外发。

### 0.2 检查内容数据

- 打开 `data/cases.json`，确认 case 文本、chart snapshot、AI draft、guardrail 文本都和论文方案一致。
- 如要修改任何内容：**只改 JSON 文件，不要改组件代码**。
- 修改完跑：

```bash
pnpm validate-data    # 检查格式与顺序约束
pnpm db:reset         # 仅 pilot 期可用！正式实验启动后慎用
```

### 0.3 跑一次 pilot

- 自己（或 RA）以"参与者"身份从 `/` 走完整个流程，时长应在 28–32 分钟。
- 进入 `/admin/export?token=...`，确认能看到混淆矩阵和 per-case 表。
- 跑一次：

```bash
node scripts/sanity-check.mjs
```

确保输出底部是 `✅ All checks passed.`。

---

## 阶段 1 · 招募 & 邀请

### 1.1 给医生的邀请话术（示例）

> 你好医生，邀请您参与一个约 30 分钟的脚本化研究。任务是审核几个虚构 patient portal 消息的 AI 草稿回复，并决定是否可以发送。所有 case 都是虚构的，不涉及任何真实病人。完成后会有 completion code。
>
> 请用电脑端 Chrome / Edge / Safari 浏览器打开下方链接（手机/iPad 体验较差，不建议）：
>
> https://你的域名/

### 1.2 不要在邀请里告诉医生什么

- 不要说"我们想看你能不能发现 AI 的错"，否则医生会进入"找错"模式，破坏生态效度。
- 不要说"有些 case AI 是错的"，让医生像平时一样审核。
- **同意页文本已经处理好了这一点**，照样发链接即可。

---

## 阶段 2 · 实验进行中

### 2.1 监控完成率

定期跑：

```bash
node scripts/sanity-check.mjs
```

输出会包含：

- 总参与者 / 完成数 / 完成率
- 按 condition 分组的人数（应大致 50/50）
- 按 orderTemplate 分组的人数（4 套应大致均匀）
- 每个 case 的最大/中位/最小时长
- 数据完整性：是否有空 finalReplyText / 缺 caseSurvey 等
- 整体 accuracy + unsafe send-as-is + appropriate escalation
- UI 事件总数

### 2.2 condition 不平衡怎么办

如果某个 condition 招到 6 个、另一个只 2 个，可在 `src/lib/randomization.ts` 改成 **block randomization**（每 4 人保证 2:2）。这是个 5 行小改动，让开发同学帮你做。

### 2.3 有人中途退出怎么办

- 中途退出的参与者会在数据库里留下 `completedFlag=false` 的记录。
- 主分析时只用 `completedFlag=true` 的样本。
- 如果某个参与者只完成 3 个 case 就离开，他们的 `case_presentations` 仍会被保留，可用于 dropout 分析。

---

## 阶段 3 · 收数据

### 3.1 哪里下载

进入 `/admin/export?token=你的ADMIN_TOKEN`，页面下方有 8 个表格，每个都可下载 CSV / JSON：

| 表 | 用来做什么 |
| --- | --- |
| `participants` | 人口学 + condition + orderTemplate + 完成时间 |
| `sessions` | 会话开始/结束/状态 |
| `case_presentations` | 谁在第几个看到了哪个 case + duration |
| **`actions`** | **最重要**：4 种动作 / final_reply_text / edit_distance / goldAction / goldActionMatch / clientStatsJson |
| `case_surveys` | 每个 case 后的 3 个量表题 |
| `post_surveys` | 整体后测（按 block 存 JSON） |
| `ui_events` | 全量点击/切焦/编辑日志（HCI 论文很值钱） |
| `summary` | 混淆矩阵 + per-case + per-participant 打分量表 |

### 3.2 一次性导出全部数据（推荐）

```bash
TOKEN=你的ADMIN_TOKEN
HOST=https://你的域名
mkdir -p export-$(date +%Y%m%d)
cd export-$(date +%Y%m%d)
for t in participants sessions case_presentations actions case_surveys post_surveys ui_events summary; do
  for f in csv json; do
    curl -sf "$HOST/api/admin/export?token=$TOKEN&table=$t&format=$f" -o "$t.$f"
    echo "  saved $t.$f"
  done
done
```

### 3.3 数据字典

#### `actions` 表（最关键）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `actionId` | string | action 唯一 ID |
| `participantId` | string | 参与者 ID |
| `caseId` | string | 案例 ID |
| `orderIndex` | int | 第几个看到（0–7；练习为 -1） |
| `selectedAction` | enum | `send_as_is / edit_then_send / discard_and_rewrite / escalate` |
| `sendAsIsFlag / editFlag / discardFlag / escalateFlag` | bool | one-hot |
| `escalateSubtype` | string? | 升级类型（urgent_evaluation / call_patient / ed_instruction / other） |
| `finalReplyText` | string | **医生最终发出的文本**（行为 outcome 真相） |
| `finalReplyCharCount` | int | 字符数 |
| `editDistance` | int | 与 AI draft 的 Levenshtein 距离（edit intensity） |
| `goldAction` | enum | 该 case 的"理想动作" |
| `goldActionMatch` | bool | selectedAction 是否在 gold 或 alternates 内 |
| `clientStatsJson` | JSON | timeToFirstClickMs / panelClickCounts / checklistChecked / editKeystrokes / pageBlurCount 等 |
| `serverReceivedAt` | datetime | 后端收到的时间（唯一真相） |

#### `summary` 表

- `kind=completion`：总参与者 / 完成数 / 完成率 / 整体 accuracy
- `kind=confusion_matrix`：4×4 混淆矩阵的每个 cell（goldAction × selectedAction × count）
- `kind=per_case`：每个 case 的 matchGold / unsafeSendAsIs / errorSurvival / appropriateEscalation / meanDurationMs / meanEditDistance
- `kind=per_participant`：每个参与者的 accuracy / errorSurvivalCount / meanDurationMs / meanEditDistance

---

## 阶段 4 · 分析建议

### 4.1 Paper 1（行为）核心 outcome

| Outcome | 怎么算 | 数据来源 |
| --- | --- | --- |
| **error survival** | defective case 中医生没纠错的比例 | `case_presentations` join `cases` join `actions`：where `defectPresent=true` and `goldActionMatch=false` |
| **unsafe send-as-is** | defective case + `sendAsIsFlag=true` 的数量 | 同上 |
| **appropriate escalation** | gold=escalate 的 case 中 `escalateFlag=true` 的比例 | 同上 |
| **edit intensity** | `editDistance` 的均值（按 condition 分组） | `actions` |
| **verification behavior** | guardrail 组中 `clientStatsJson.panelClickCounts.facts_panel` > 0 的比例 | `actions` |
| **case duration** | `case_presentations.durationMs` 均值 | `case_presentations` |

### 4.2 主分析模型（建议）

混合效应 logistic / linear regression，固定效应：condition（plain vs guardrail），随机效应：participant、case。

```r
# error_survival 例子
library(lme4)
m1 <- glmer(
  goldActionMatch ~ condition + (1|participantId) + (1|caseId),
  data = subset(actions, defectPresent == TRUE),
  family = binomial
)
summary(m1)
```

### 4.3 Paper 2（态度）核心问题

把 `post_surveys.payloadJson` 解析出 5 个 block（trust / transparency / workflow / accountability / overreliance），分别求 block 均值。

然后做相关分析：

| 关系 | 假设 |
| --- | --- |
| trust × send_as_is 比例 | 高 trust 是否预测更多 send-as-is？ |
| transparency × verification | guardrail 组的 transparency 是否更高？是否更多查看 facts？ |
| overreliance concern × edit_distance | 担心 overreliance 的人是否改得更多？ |
| accountability × unsafe send-as-is | 高 accountability 是否减少 unsafe send？ |

### 4.4 老师建议的混淆矩阵 + 打分量表

`/admin/export` 页面顶部已经直接给出。或者用 `summary` 表：

```python
import pandas as pd
df = pd.read_csv("summary.csv")
cm = df[df.kind == "confusion_matrix"]
mat = cm.pivot(index="goldAction", columns="selectedAction", values="count").fillna(0)
print(mat)
print("Accuracy:", df[df.kind == "completion"]["accuracy"].iloc[0])
```

---

## 阶段 5 · 数据归档

实验结束后建议做一次完整快照：

```bash
# 1) 导出所有 8 张表的 CSV + JSON
# (用上面 3.2 的脚本)

# 2) 备份 SQLite 数据库
cp prisma/dev.db backup-$(date +%Y%m%d).db

# 3) commit 一份不含 PHI 的 demographics summary
node scripts/sanity-check.mjs > sanity-$(date +%Y%m%d).txt

# 4) 上传到机构合规数据存储（不要放 GitHub 公仓）
```

---

## 常见问题

**Q：参与者反映页面卡住怎么办？**
A：让他们刷新页面 —— 状态机会自动恢复到当前 case。如果还卡，请他们换 Chrome / Edge。

**Q：参与者意外关闭浏览器，数据丢了吗？**
A：不会丢。每个 case 提交都立刻写入数据库；整体 session 也会留 `completedFlag=false` 的记录。

**Q：`pnpm db:reset` 会清空所有数据吗？**
A：会！只在 pilot 期使用。实验启动后只用 `pnpm db:seed`（不会清旧数据，只 upsert case 内容）。

**Q：能切换到 PostgreSQL 吗？**
A：可以。改 `prisma/schema.prisma` 里的 `provider = "postgresql"`，把 `DATABASE_URL` 指向 PG，再跑 `pnpm db:push`。所有代码不需要改。

**Q：能加 live API 模式做 Paper 2 扩展吗？**
A：能。原始方案已经留好 `mode_live_explanation` 扩展位 —— 加一个 condition、一个 API 路由、复用 CasePage 即可。建议正式做时先开新分支。
