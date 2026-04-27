# `data/` —— 实验内容数据层（唯一真相）

这一层是**整个平台的内容真相**。前端组件不应该硬编码任何 case 文本、量表题或顺序。

## 文件清单

| 文件 | 说明 |
| --- | --- |
| `cases.json` | 1 个练习 case + 8 个正式 case 的全部内容（patient message / chart snapshot / AI draft / guardrail / gold action） |
| `order_templates.json` | 4 套 case 顺序模板，进入实验时随机分配 |
| `case_quick_survey.json` | 每个 case 后的 3 个 1–7 量表题 |
| `pre_survey.json` | 前测问卷题目结构 |
| `post_survey.json` | 后测问卷分 block 题目结构（trust / transparency / workflow / accountability / overreliance） |

## 修改 case 数量

PI 想加/减 case：

1. 修改 `cases.json` 中正式 case 的数量。
2. 修改 `order_templates.json` 让每个模板的 `order` 长度匹配新数量。
3. 跑 `node scripts/validate-data.mjs` 确认通过。
4. 重新跑 prisma seed（Phase 1 后续阶段加上）。

## 修改顺序模板

请保持以下硬约束：

- 不要让 ≥3 个 defective case 连续；
- 不要让所有高风险 case 都集中在后半段；
- 不要让所有低风险准确 case 全在前半段。

`scripts/validate-data.mjs` 会自动检查。

## 修改量表题

- 量表统一 1–7 分，min/max label 在 JSON 顶部统一定义。
- 加题时给一个稳定的 `id`（写入数据库的 key）。
- 加题不要破坏既有 id，避免老数据无法对齐。

## defective / risk 标注约定

- `defectPresent: true` 表示这个 case 的 AI draft 存在问题；分析时计算 error survival。
- `riskLevel`: `"low" | "medium_low" | "medium" | "medium_high" | "high"`。
- `defectType` 字段命名见现有 case，便于做分组统计。
