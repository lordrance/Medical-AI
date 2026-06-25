// k6 load test for Medical-AI V4 (deployed production)
// Simulates real doctor behavior: consent → fill surveys → review 8 cases
//
// Usage:
//   k6 run --vus 10 --duration 60s tests/load/k6-v4-smoke.js
//   k6 run --vus 50 --duration 120s tests/load/k6-v4-smoke.js
//   k6 run --vus 100 --duration 120s tests/load/k6-v4-smoke.js

import http from "k6/http";
import { check, sleep, group } from "k6";

const BASE = __ENV.BASE_URL || "https://101-32-216-183.nip.io";

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.05"],    // < 5% errors
    http_req_duration: ["p(95)<3000"], // P95 < 3s
  },
};

export default function () {
  const headers = { "Content-Type": "application/json" };

  // Step 1: Create session (each VU = one participant)
  let sessionRes = http.post(`${BASE}/api/session`, "{}", { headers, tags: { name: "create-session" } });
  check(sessionRes, { "session created": (r) => r.status === 200 });

  if (sessionRes.status !== 200) { return; }
  const session = sessionRes.json();
  const sid = session.sessionId;
  const cases = session.caseOrder;  // 8 cases in random order

  // Step 2: Load and submit each case
  for (let i = 0; i < cases.length; i++) {
    const cid = cases[i];

    // 2a: Get case details
    let caseRes = http.get(`${BASE}/api/case/${cid}?sessionId=${sid}`, { headers, tags: { name: "get-case" } });
    check(caseRes, { [`case ${i} loaded`]: (r) => r.status === 200 });
    if (caseRes.status !== 200) continue;

    // 2b: Open case (start timing)
    let openRes = http.post(`${BASE}/api/case/open`, JSON.stringify({
      sessionId: sid, caseId: cid, orderIndex: i,
    }), { headers, tags: { name: "open-case" } });
    check(openRes, { [`case ${i} opened`]: (r) => r.status === 200 });
    if (openRes.status !== 200) continue;

    // 2c: Submit action (simulate doctor decision)
    let actionRes = http.post(`${BASE}/api/action`, JSON.stringify({
      sessionId: sid,
      caseId: cid,
      orderIndex: i,
      isPractice: false,
      selectedAction: "edit_then_send",
      finalReplyText: "已根据患者情况调整用药方案。",
      caseActionReasonCode: "basically_ok",
      quickSurvey: { caseDecisionConfidence: 4, caseDraftHelpfulness: 3 },
      timing: { startedAt: Date.now() - 60000, endedAt: Date.now(), durationMs: 60000 },
    }), { headers, tags: { name: "submit-action" } });
    check(actionRes, { [`case ${i} submitted`]: (r) => r.status === 200 });

    // Simulate doctor reading time between cases (2-5 seconds)
    sleep(Math.random() * 3 + 2);
  }

  // Step 3: Submit surveys
  let preSurveyRes = http.post(`${BASE}/api/pre-survey`, JSON.stringify({
    sessionId: sid,
    preSpecialty: "internal_medicine",
    preTrainingLevel: "attending",
    preYearsPostResidency: 5,
    preWeeklyMsgVolume: 100,
    preAiDraftingFamiliarity: 3,
  }), { headers, tags: { name: "pre-survey" } });
  check(preSurveyRes, { "pre-survey ok": (r) => r.status === 200 });

  let postSurveyRes = http.post(`${BASE}/api/post-survey`, JSON.stringify({
    sessionId: sid,
    participantId: session.participantId,
    payload: {
      attn_post_1: 4,
      post_qual_l1_ehr_pain_ai_substitution: "EHR记录耗时过长，AI可协助初步整理。",
      post_qual_l2_human_ai_boundary: "AI可处理常规回复，复杂病情需医生决策。",
      post_qual_l3_system_transformation: "AI将改变医患沟通方式，提高效率。",
    },
  }), { headers, tags: { name: "post-survey" } });
  check(postSurveyRes, { "post-survey ok": (r) => r.status === 200 });
}
