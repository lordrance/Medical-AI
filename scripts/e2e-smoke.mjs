#!/usr/bin/env node
/**
 * 端到端 smoke test：模拟一个参与者完成全部 8 个 case，验证：
 *  - /api/session 创建成功
 *  - /api/pre-survey 接受
 *  - /api/case/[id] 按 condition 返回字段
 *  - /api/action 接受 4 种动作 + clientStats，并返回 editDistance
 *  - /api/post-survey 接受
 *  - /api/admin/summary 返回非空
 *
 * 用法: BASE=http://localhost:3000 ADMIN_TOKEN=xxx node scripts/e2e-smoke.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE ?? "http://localhost:3000";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN ?? "change-me-in-production";

const cases = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "..", "data", "cases.json"), "utf-8"),
);
const goldByCaseId = Object.fromEntries(
  cases.map((c) => [c.id, c.goldAction]),
);

async function jpost(path, body) {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}
async function jget(path) {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function simulate(label, actionPicker) {
  console.log(`\n=== Simulating: ${label} ===`);
  const session = await jpost("/api/session", {});
  console.log(
    `  session=${session.sessionId.slice(-8)} cond=${session.condition} tpl=${session.orderTemplateId}`,
  );
  await jpost("/api/pre-survey", {
    sessionId: session.sessionId,
    answers: {
      specialty: "Internal Medicine",
      training_level: "Attending",
      years_practice: 5,
      weekly_message_volume: "11–25",
      prior_ai_use: "Weekly",
      ai_familiarity: 5,
    },
  });

  const ids = [session.practiceCaseId, ...session.caseOrder];
  for (let i = 0; i < ids.length; i++) {
    const caseId = ids[i];
    const isPractice = i === 0;
    const orderIndex = isPractice ? -1 : i - 1;
    const c = await jget(
      `/api/case/${caseId}?sessionId=${session.sessionId}`,
    );
    const action = actionPicker(c.case);
    const startedAt = Date.now() - 5000;
    const endedAt = Date.now();
    const finalReplyText =
      action === "send_as_is"
        ? c.case.aiDraft
        : action === "edit_then_send"
          ? c.case.aiDraft + " Please call us if it gets worse."
          : action === "discard_and_rewrite"
            ? "Thanks for reaching out. Please come in today for evaluation."
            : "[escalated]";
    const r = await jpost("/api/action", {
      sessionId: session.sessionId,
      caseId,
      orderIndex,
      isPractice,
      selectedAction: action,
      finalReplyText,
      escalateSubtype: action === "escalate" ? "urgent_evaluation" : undefined,
      quickSurvey: { item1: 5, item2: 6, item3: 4 },
      timing: { startedAt, endedAt, durationMs: endedAt - startedAt },
      clientStats: {
        timeToFirstClickMs: 800,
        panelClickCounts: { ai_draft_panel: 1, action_panel: 1 },
        checklistChecked: c.case.guardrail
          ? c.case.guardrail.checklist.map(() => true)
          : [],
        checklistToggleCount: c.case.guardrail
          ? c.case.guardrail.checklist.length
          : 0,
        editKeystrokes: action === "edit_then_send" ? 12 : 0,
        editBoxOpenedCount: action === "edit_then_send" || action === "discard_and_rewrite" ? 1 : 0,
        pageBlurCount: 0,
        pageFocusCount: 0,
        visibilityHiddenMs: 0,
      },
    });
    console.log(
      `  ${isPractice ? "P" : i - 1}. ${caseId.padEnd(15)} ${action.padEnd(20)} ed=${r.editDistance}`,
    );
  }
  await jpost("/api/post-survey", {
    sessionId: session.sessionId,
    payload: {
      trust_1: 5, trust_2: 4, trust_3: 5,
      transparency_1: 4, transparency_2: 4, transparency_3: 4,
      workflow_1: 5, workflow_2: 5, workflow_3: 3,
      accountability_1: 7, accountability_2: 6, accountability_3: 5,
      overreliance_1: 5, overreliance_2: 4, overreliance_3: 5,
      open_1: "test", open_2: "test",
    },
  });
  return session;
}

const goldPicker = (c) => goldByCaseId[c.id] ?? "send_as_is";
const lazyPicker = () => "send_as_is";

(async () => {
  await simulate("perfect (gold)", goldPicker);
  await simulate("perfect (gold) #2", goldPicker);
  await simulate("lazy (always send-as-is)", lazyPicker);

  const summary = await fetch(
    `${BASE}/api/admin/summary?token=${encodeURIComponent(ADMIN_TOKEN)}`,
  );
  if (!summary.ok) {
    throw new Error(`summary HTTP ${summary.status}: ${await summary.text()}`);
  }
  const data = await summary.json();
  console.log("\n=== Summary ===");
  console.log(
    `  participants: ${data.completion.completed}/${data.completion.totalParticipants}`,
  );
  console.log(
    `  accuracy: ${(data.confusionMatrix.accuracy * 100).toFixed(1)}% (n=${data.confusionMatrix.total})`,
  );
  console.log(`  per case rows: ${data.perCase.length}`);
  console.log(`  per participant rows: ${data.perParticipant.length}`);
  console.log("\nConfusion matrix:");
  console.log("  rows = gold, cols = selected; actions:", data.confusionMatrix.actions);
  for (let i = 0; i < data.confusionMatrix.actions.length; i++) {
    console.log(
      `  ${data.confusionMatrix.actions[i].padEnd(20)} ${data.confusionMatrix.matrix[i].join("\t")}`,
    );
  }
  console.log("\n✅ smoke OK");
})();
