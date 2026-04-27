#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.resolve(__dirname, "..", "data");

function read(file) {
  return JSON.parse(fs.readFileSync(path.join(dataDir, file), "utf-8"));
}

const cases = read("cases.json");
const orderTemplates = read("order_templates.json");
const preSurvey = read("pre_survey.json");
const postSurvey = read("post_survey.json");
const caseQuickSurvey = read("case_quick_survey.json");

const errors = [];
const warn = [];

const officialIds = cases.filter((c) => !c.isPractice).map((c) => c.id);
const defectiveIds = new Set(
  cases.filter((c) => !c.isPractice && c.defectPresent).map((c) => c.id),
);
const highRiskIds = new Set(
  cases.filter((c) => !c.isPractice && c.riskLevel === "high").map((c) => c.id),
);
const lowRiskIds = new Set(
  cases.filter((c) => !c.isPractice && c.riskLevel === "low").map((c) => c.id),
);

if (officialIds.length !== 8) {
  errors.push(`正式 case 数量应为 8，实际 ${officialIds.length}`);
}

const requiredCaseFields = [
  "id",
  "isPractice",
  "riskLevel",
  "defectPresent",
  "patientMessage",
  "chartSnapshot",
  "aiDraft",
  "guardrail",
  "goldAction",
];
for (const c of cases) {
  for (const f of requiredCaseFields) {
    if (c[f] === undefined || c[f] === null) {
      errors.push(`case ${c.id} 缺少字段 ${f}`);
    }
  }
  if (c.guardrail) {
    if (!Array.isArray(c.guardrail.factsUsed) || c.guardrail.factsUsed.length === 0) {
      errors.push(`case ${c.id} guardrail.factsUsed 为空`);
    }
    if (!c.guardrail.riskCue) {
      errors.push(`case ${c.id} guardrail.riskCue 为空`);
    }
    if (!Array.isArray(c.guardrail.checklist) || c.guardrail.checklist.length < 3) {
      errors.push(`case ${c.id} guardrail.checklist 应至少 3 条`);
    }
  }
  const allowedActions = new Set([
    "send_as_is",
    "edit_then_send",
    "discard_and_rewrite",
    "escalate",
  ]);
  if (!allowedActions.has(c.goldAction)) {
    errors.push(`case ${c.id} goldAction 不在四种动作内`);
  }
}

if (!Array.isArray(orderTemplates.templates) || orderTemplates.templates.length !== 4) {
  errors.push(`需要 4 套顺序模板，实际 ${orderTemplates.templates?.length}`);
}

for (const t of orderTemplates.templates) {
  if (t.order.length !== 8) {
    errors.push(`模板 ${t.id} 顺序长度应为 8`);
  }
  const set = new Set(t.order);
  if (set.size !== t.order.length) {
    errors.push(`模板 ${t.id} 包含重复 case`);
  }
  for (const id of t.order) {
    if (!officialIds.includes(id)) {
      errors.push(`模板 ${t.id} 包含未知 case ${id}`);
    }
  }

  let consecutiveDefective = 0;
  let maxConsecutiveDefective = 0;
  for (const id of t.order) {
    if (defectiveIds.has(id)) {
      consecutiveDefective += 1;
      maxConsecutiveDefective = Math.max(maxConsecutiveDefective, consecutiveDefective);
    } else {
      consecutiveDefective = 0;
    }
  }
  if (maxConsecutiveDefective >= 3) {
    errors.push(`模板 ${t.id} 出现 ${maxConsecutiveDefective} 个 defective case 连续`);
  }

  const lastHalf = t.order.slice(4);
  const highInLastHalf = lastHalf.filter((id) => highRiskIds.has(id)).length;
  const allHighInLast = highInLastHalf === highRiskIds.size;
  if (allHighInLast) {
    errors.push(`模板 ${t.id} 所有高风险 case 都集中在后半段`);
  }

  const firstHalf = t.order.slice(0, 4);
  const lowAccurateIds = [...lowRiskIds].filter((id) => !defectiveIds.has(id));
  const lowAccurateInFirstHalf = firstHalf.filter((id) => lowAccurateIds.includes(id)).length;
  if (lowAccurateInFirstHalf === lowAccurateIds.length && lowAccurateIds.length > 0) {
    warn.push(`模板 ${t.id} 所有 low-accurate case 都在前半段（建议打散）`);
  }
}

if (!Array.isArray(preSurvey.items) || preSurvey.items.length === 0) {
  errors.push("pre_survey.items 为空");
}
if (!Array.isArray(postSurvey.blocks) || postSurvey.blocks.length === 0) {
  errors.push("post_survey.blocks 为空");
}
if (!Array.isArray(caseQuickSurvey.items) || caseQuickSurvey.items.length !== 3) {
  errors.push("case_quick_survey 应有 3 个题目");
}

if (errors.length === 0) {
  console.log("✅ 数据校验通过");
  console.log(`  正式 case: ${officialIds.length}`);
  console.log(`  defective: ${defectiveIds.size}`);
  console.log(`  high-risk: ${highRiskIds.size}`);
  console.log(`  low-risk: ${lowRiskIds.size}`);
  console.log(`  顺序模板: ${orderTemplates.templates.length}`);
  if (warn.length > 0) {
    console.log("");
    console.log("⚠️  警告：");
    for (const w of warn) console.log("  -", w);
  }
  process.exit(0);
} else {
  console.error("❌ 数据校验失败：");
  for (const e of errors) console.error("  -", e);
  if (warn.length > 0) {
    console.error("");
    console.error("⚠️  另有警告：");
    for (const w of warn) console.error("  -", w);
  }
  process.exit(1);
}
