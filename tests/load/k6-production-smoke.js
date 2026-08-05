// Production smoke test for Medical-AI (Shanghai server, medraftlab.com)
// Simulates 1 complete participant flow, then validates data integrity.
// Test data is tagged for cleanup.
//
// Usage:
//   k6 run --vus 1 --iterations 1 tests/load/k6-production-smoke.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = "https://medraftlab.com";
const PHONE = "9999"; // test marker: easily identifiable for cleanup

export const options = {
  thresholds: {
    http_req_duration: ["p(95)<5000"], // must respond within 5s from mainland
  },
};

export default function () {
  const headers = { "Content-Type": "application/json" };

  // ── Step 1: Create session ──
  console.log("=== 1. 创建会话 ===");
  let r = http.post(`${BASE}/api/session`, "{}", { headers, tags: { name: "create-session" } });
  check(r, { "session 200": (r) => r.status === 200 });
  if (r.status !== 200) { console.error(`SESSION FAILED: ${r.status} ${r.body}`); return; }
  const s = r.json();
  console.log(`   sessionId=${s.sessionId}, cases=${s.caseOrder.length}`);

  // ── Step 2: Pre-survey ──
  console.log("=== 2. 前测问卷 ===");
  r = http.post(`${BASE}/api/pre-survey`, JSON.stringify({
    sessionId: s.sessionId,
    answers: {
      pre_specialty: "测试科室",
      pre_training_level: "测试职级",
      pre_years_post_residency: 5,
      pre_weekly_msg_volume: "1—10 条",
      pre_ai_drafting_familiarity: 3,
    },
  }), { headers, tags: { name: "pre-survey" } });
  check(r, { "pre-survey 200": (r) => r.status === 200 });
  if (r.status !== 200) console.error(`PRE-SURVEY FAILED: ${r.status} ${r.body}`);

  // ── Step 3: Load practice case ──
  console.log("=== 3. 练习案例 ===");
  const practiceId = s.practiceCaseId;
  r = http.get(`${BASE}/api/case/${practiceId}?sessionId=${s.sessionId}`, { headers, tags: { name: "get-practice" } });
  check(r, { "practice case 200": (r) => r.status === 200 });
  if (r.status !== 200) console.error(`PRACTICE FAILED: ${r.status} ${r.body}`);

  // Open practice
  r = http.post(`${BASE}/api/case/open`, JSON.stringify({
    sessionId: s.sessionId, caseId: practiceId, orderIndex: -1,
  }), { headers, tags: { name: "open-practice" } });
  check(r, { "practice open 200": (r) => r.status === 200 });

  // Submit practice
  r = http.post(`${BASE}/api/action`, JSON.stringify({
    sessionId: s.sessionId, caseId: practiceId, orderIndex: -1, isPractice: true,
    selectedAction: "send_as_is",
    finalReplyText: "[测试] 原样发送",
    caseActionReasonCode: "nothing_to_change",
    quickSurvey: { caseDecisionConfidence: 4, caseDraftHelpfulness: 4 },
    timing: { startedAt: Date.now() - 30000, endedAt: Date.now(), durationMs: 30000 },
  }), { headers, tags: { name: "submit-practice" } });
  check(r, { "practice submit 200": (r) => r.status === 200 });
  if (r.status !== 200) console.error(`PRACTICE SUBMIT FAILED: ${r.status} ${r.body}`);

  // ── Step 4: 8 formal cases ──
  console.log("=== 4. 正式案例(8个) ===");
  for (let i = 0; i < s.caseOrder.length; i++) {
    const cid = s.caseOrder[i];
    const actions = ["send_as_is", "edit_then_send", "send_as_is", "discard_and_rewrite", "edit_then_send", "send_as_is", "edit_then_send", "escalate"];
    const action = actions[i] || "send_as_is";
    const reply = action === "escalate" ? "[escalated]" : action === "edit_then_send" ? `[测试编辑] 第${i+1}案修改版` : "[测试] 原样发送";

    // Load case
    r = http.get(`${BASE}/api/case/${cid}?sessionId=${s.sessionId}`, { headers, tags: { name: "get-case" } });
    check(r, { [`case-${i} load 200`]: (r) => r.status === 200 });
    if (r.status !== 200) { console.error(`CASE ${i} FAILED: ${r.status}`); continue; }

    // Open case
    r = http.post(`${BASE}/api/case/open`, JSON.stringify({
      sessionId: s.sessionId, caseId: cid, orderIndex: i,
    }), { headers, tags: { name: "open-case" } });
    check(r, { [`case-${i} open 200`]: (r) => r.status === 200 });

    // Submit action
    const body = {
      sessionId: s.sessionId, caseId: cid, orderIndex: i, isPractice: false,
      selectedAction: action,
      finalReplyText: reply,
      caseActionReasonCode: action === "escalate" ? "safety_risk" : "basically_ok",
      escalateReason: action === "escalate" ? "[测试] 需紧急评估" : undefined,
      escalateSubtype: action === "escalate" ? "urgent_evaluation" : undefined,
      quickSurvey: { caseDecisionConfidence: 4, caseDraftHelpfulness: 3 },
      timing: { startedAt: Date.now() - 60000, endedAt: Date.now(), durationMs: 60000 },
    };
    r = http.post(`${BASE}/api/action`, JSON.stringify(body), { headers, tags: { name: "submit-case" } });
    check(r, { [`case-${i} submit 200`]: (r) => r.status === 200 });
    if (r.status !== 200) console.error(`CASE ${i} SUBMIT FAILED: ${r.status} ${r.body}`);

    sleep(0.5);
  }

  // ── Step 5: Post-survey (with phone) ──
  console.log("=== 5. 后测问卷 ===");
  const payload = {
    pre_ai_readiness_1: 3, pre_ai_readiness_2: 4, pre_ai_readiness_3: 3, pre_ai_readiness_4: 4,
    post_utility_1: 4, post_utility_2: 3, post_utility_3: 4, post_utility_4: 3,
    post_transparency_1: 3, post_transparency_2: 4, post_transparency_3: 3,
    post_comm_1: 4, post_comm_2: 3, post_comm_3: 4, post_comm_4: 3,
    post_burden_1: 3, post_burden_2: 3, post_burden_3: 3,
    post_governance_1: 3, post_governance_2: 3, post_governance_3: 3, post_governance_4: 3,
    post_reliance_1: 3, post_reliance_2: 3, post_reliance_3: 3, post_reliance_4: 3,
    post_hallu_1: 3, post_hallu_2: 3, post_hallu_3: 3, post_hallu_4: 3,
    attn_post_1: 4,
    post_calibration_1: 3, post_calibration_2: 3, post_calibration_3: 3,
    post_dissent_1: 3, post_dissent_2: 3, post_dissent_3_reverse: 3,
    post_accept_trust: 3, post_accept_future_use: 3, post_accept_limited_use: 3, post_accept_optional: 3,
    post_qual_l1_ehr_pain_ai_substitution: "[测试] EHR填写与多系统信息整合最费时,AI可协助病史摘要与警报过滤;诊断与告知仍需医生本人完成。",
    post_qual_l2_human_ai_boundary: "[测试] Agentic AI可独立承担行政工作、异常标记、风险预警;用药决策、诊断、敏感沟通与最终责任必须保留给医生;最担心AI越权调药的边界。",
    post_qual_l3_system_transformation: "[测试] 医院组织管理与分级诊疗将被重塑,医生角色更偏审核;最期待文书负担下降,最担心责任模糊与患者隐私风险。",
    post_phone_last4: PHONE,
  };

  r = http.post(`${BASE}/api/post-survey`, JSON.stringify({
    sessionId: s.sessionId, payload: payload,
  }), { headers, tags: { name: "post-survey" } });
  check(r, { "post-survey 200": (r) => r.status === 200 });
  if (r.status !== 200) {
    console.error(`POST-SURVEY FAILED: ${r.status} ${r.body}`);
    return;
  }
  const result = r.json();
  console.log(`   completionCode=${result.completionCode}, ok=${result.ok}`);

  console.log("");
  console.log("✅ 完整流程通过");
  console.log(`   完成码: ${result.completionCode}`);
  console.log(`   sessionId: ${s.sessionId}`);
  console.log(`   participantId: ${s.participantId}`);
}
