#!/usr/bin/env node
/**
 * Sanity check：扫描数据库，输出实验数据的健康报告。
 * 用法：node scripts/sanity-check.mjs
 *
 * 检查项：
 *  - 完成率（按 condition 分组）
 *  - 每个完成参与者的总时长（应在 ~30min 之间）
 *  - 每个 case 的最大/最小/中位时长
 *  - 是否有参与者完成了 case 但 finalReplyText 为空
 *  - 是否有 caseSurvey 缺失
 *  - 顺序模板分布是否平衡（4 套模板）
 *  - condition 分布是否平衡
 *  - 整体准确率与混淆矩阵摘要
 *  - 异常 case 列表（duration > 8min 或 < 5s）
 */
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

function median(arr) {
  if (arr.length === 0) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid];
}
function fmtMs(ms) {
  if (!ms && ms !== 0) return "—";
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}min`;
}

async function main() {
  const issues = [];
  const warnings = [];

  console.log("================================================");
  console.log("  Medical-AI · Experiment Data Sanity Check");
  console.log("================================================\n");

  const participants = await prisma.participant.findMany();
  const completed = participants.filter((p) => p.completedFlag);
  const completionRate = participants.length
    ? (completed.length / participants.length) * 100
    : 0;

  console.log("【1】Completion");
  console.log(
    `  total: ${participants.length}   completed: ${completed.length} (${completionRate.toFixed(1)}%)`,
  );

  const condCount = participants.reduce((m, p) => {
    m[p.condition] = (m[p.condition] || 0) + 1;
    return m;
  }, {});
  console.log(`  by condition: ${JSON.stringify(condCount)}`);

  const tplCount = participants.reduce((m, p) => {
    m[p.orderTemplateId] = (m[p.orderTemplateId] || 0) + 1;
    return m;
  }, {});
  console.log(`  by orderTemplate: ${JSON.stringify(tplCount)}`);

  const condCounts = Object.values(condCount);
  if (condCounts.length === 2 && Math.abs(condCounts[0] - condCounts[1]) > Math.max(3, participants.length * 0.2)) {
    warnings.push(
      `Condition imbalance: ${JSON.stringify(condCount)} (差值 > 20% 或 > 3)`,
    );
  }

  const sessions = await prisma.session.findMany();
  const completedSessions = sessions.filter((s) => s.endedAt);
  const sessionDurations = completedSessions
    .map((s) => s.endedAt.getTime() - s.startedAt.getTime())
    .sort((a, b) => a - b);

  console.log("\n【2】Session duration (only completed)");
  console.log(`  n: ${sessionDurations.length}`);
  if (sessionDurations.length > 0) {
    console.log(`  min:    ${fmtMs(sessionDurations[0])}`);
    console.log(`  median: ${fmtMs(median(sessionDurations))}`);
    console.log(`  max:    ${fmtMs(sessionDurations[sessionDurations.length - 1])}`);
    const overlong = completedSessions.filter(
      (s) => s.endedAt.getTime() - s.startedAt.getTime() > 35 * 60_000,
    );
    if (overlong.length > 0) {
      warnings.push(
        `${overlong.length} session(s) > 35min — 检查这些参与者是否被打断或题目过难`,
      );
    }
    const tooShort = completedSessions.filter(
      (s) => s.endedAt.getTime() - s.startedAt.getTime() < 5 * 60_000,
    );
    if (tooShort.length > 0) {
      warnings.push(
        `${tooShort.length} session(s) < 5min — 可能是机器人或测试数据`,
      );
    }
  }

  console.log("\n【3】Per-case duration (formal cases only)");
  const presentations = await prisma.casePresentation.findMany({
    include: { case: true, action: true, caseSurvey: true },
  });
  const formal = presentations.filter((p) => !p.case.isPractice);
  const byCase = new Map();
  for (const p of formal) {
    if (!byCase.has(p.caseId)) byCase.set(p.caseId, []);
    if (typeof p.durationMs === "number") byCase.get(p.caseId).push(p.durationMs);
  }
  const sortedCaseIds = [...byCase.keys()].sort();
  for (const cid of sortedCaseIds) {
    const arr = byCase.get(cid);
    if (arr.length === 0) continue;
    const sorted = [...arr].sort((a, b) => a - b);
    console.log(
      `  ${cid.padEnd(10)} n=${String(arr.length).padStart(3)}  min=${fmtMs(sorted[0]).padEnd(7)} median=${fmtMs(median(arr)).padEnd(7)} max=${fmtMs(sorted[sorted.length - 1])}`,
    );
  }

  console.log("\n【4】Data integrity");

  const formalActions = formal.filter((p) => p.action != null);
  const noAction = formal.filter((p) => p.action == null);
  if (noAction.length > 0) {
    issues.push(
      `${noAction.length} case presentations 没有 action 记录（应为 0）`,
    );
  }
  console.log(`  presentations with action:   ${formalActions.length}`);
  console.log(`  presentations missing action: ${noAction.length}`);

  const emptyFinal = formalActions.filter(
    (p) => !p.action.finalReplyText || p.action.finalReplyText.trim() === "",
  );
  if (emptyFinal.length > 0) {
    issues.push(`${emptyFinal.length} actions 的 finalReplyText 为空`);
  }
  console.log(`  empty finalReplyText:        ${emptyFinal.length}`);

  const noSurvey = formal.filter((p) => p.caseSurvey == null);
  if (noSurvey.length > 0) {
    issues.push(`${noSurvey.length} case presentations 缺 caseSurvey`);
  }
  console.log(`  presentations missing case survey: ${noSurvey.length}`);

  const fast = formalActions.filter((p) => (p.durationMs ?? 0) < 5_000);
  const slow = formalActions.filter((p) => (p.durationMs ?? 0) > 8 * 60_000);
  console.log(`  case duration < 5s:          ${fast.length} (异常快)`);
  console.log(`  case duration > 8min:        ${slow.length} (异常慢)`);
  if (fast.length > formalActions.length * 0.1 && formalActions.length > 0) {
    warnings.push(
      `>10% 的 case 完成时间 < 5s，可能是医生跳过或测试数据`,
    );
  }

  console.log("\n【5】Overall accuracy");
  let total = 0;
  let matchGold = 0;
  let unsafeSendAsIs = 0;
  let appropriateEscalation = 0;
  let escalateNeeded = 0;
  for (const p of formalActions) {
    total += 1;
    const gold = p.case.goldAction;
    const sel = p.action.selectedAction;
    if (gold === sel) matchGold += 1;
    if (p.case.defectPresent && p.action.sendAsIsFlag) unsafeSendAsIs += 1;
    if (gold === "escalate") {
      escalateNeeded += 1;
      if (p.action.escalateFlag) appropriateEscalation += 1;
    }
  }
  if (total > 0) {
    console.log(`  accuracy:                    ${((matchGold / total) * 100).toFixed(1)}% (${matchGold}/${total})`);
    console.log(`  unsafe send-as-is:           ${unsafeSendAsIs}  (defective AI 草稿被原样发送)`);
    if (escalateNeeded > 0) {
      console.log(
        `  appropriate escalation:      ${appropriateEscalation}/${escalateNeeded} (${((appropriateEscalation / escalateNeeded) * 100).toFixed(1)}%)`,
      );
    }
  } else {
    console.log("  no formal action data yet");
  }

  console.log("\n【6】UI events");
  const eventCount = await prisma.uiEvent.count();
  const distinct = await prisma.uiEvent.findMany({
    distinct: ["eventType"],
    select: { eventType: true },
  });
  console.log(`  total events:                ${eventCount}`);
  console.log(`  distinct event types:        ${distinct.map((d) => d.eventType).join(", ") || "—"}`);
  if (eventCount === 0 && participants.length > 0) {
    issues.push("没有 UI event 记录 — sendBeacon 可能失败，导出会很弱");
  }

  console.log("\n================================================");
  if (issues.length === 0 && warnings.length === 0) {
    console.log("✅ All checks passed.");
  } else {
    if (issues.length > 0) {
      console.log("❌ Issues:");
      for (const x of issues) console.log("  -", x);
    }
    if (warnings.length > 0) {
      console.log("⚠️  Warnings:");
      for (const x of warnings) console.log("  -", x);
    }
  }
  console.log("================================================");

  await prisma.$disconnect();
  process.exit(issues.length > 0 ? 1 : 0);
}

main().catch(async (e) => {
  console.error(e);
  await prisma.$disconnect();
  process.exit(2);
});
