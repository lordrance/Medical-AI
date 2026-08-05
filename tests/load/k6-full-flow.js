// 100-concurrent-user full participant flow, against the disposable local
// stack in docker-compose.loadtest.yml (NOT production — this writes ~100
// fake participants per run).
//
//   docker compose -f tests/load/docker-compose.loadtest.yml up -d --build
//   k6 run tests/load/k6-full-flow.js
//
// Every virtual user walks the real journey: session → pre-survey → practice
// → 8 formal cases → post-survey → completion code.
//
// 20% of submits are sent twice back-to-back. That is not artificial: the
// frontend gives up on a stalled request after 25s and the participant taps
// 提交 again while the first request is still running server-side. Both
// copies must return 200 and the second must not create a duplicate row.

import http from "k6/http";
import { check, sleep, fail } from "k6";
import { Counter, Rate } from "k6/metrics";

const BASE = __ENV.BASE || "http://localhost:8001";
const DOUBLE_SUBMIT_RATE = Number(__ENV.DOUBLE_SUBMIT_RATE ?? 0.2);
// VERIFY=1 runs a handful of full flows instead of the 100-VU ramp — used to
// confirm a deploy on the real server without writing 2000 fake participants.
const VERIFY = __ENV.VERIFY === "1";

const serverErrors = new Counter("server_errors_5xx");
const dupMismatch = new Counter("duplicate_submit_mismatch");
const flowCompleted = new Rate("flow_completed");

const thresholds = {
  http_req_failed: ["rate<0.01"],
  http_req_duration: [`p(95)<${VERIFY ? 5000 : 2000}`], // cross-country adds latency
  server_errors_5xx: ["count==0"],
  duplicate_submit_mismatch: ["count==0"],
  flow_completed: ["rate>0.99"],
};

export const options = VERIFY
  ? { vus: 3, iterations: 3, thresholds }
  : {
      stages: [
        { duration: "30s", target: 100 }, // everyone arrives
        { duration: "2m", target: 100 },  // 100 concurrently working
        { duration: "20s", target: 0 },
      ],
      thresholds,
    };

const headers = { "Content-Type": "application/json" };

/** POST + record 5xx separately: a 5xx is a bug, a timeout is a capacity limit. */
function post(path, body, name) {
  const r = http.post(`${BASE}${path}`, JSON.stringify(body), {
    headers,
    tags: { name },
  });
  if (r.status >= 500) {
    serverErrors.add(1);
    console.error(`5xx on ${name}: ${r.status} ${String(r.body).slice(0, 300)}`);
  }
  return r;
}

/** Submit, then (sometimes) submit the identical body again as a retry would. */
function postMaybeTwice(path, body, name) {
  const first = post(path, body, name);
  if (Math.random() < DOUBLE_SUBMIT_RATE) {
    const second = post(path, body, `${name}-retry`);
    if (second.status !== first.status) {
      dupMismatch.add(1);
      console.error(
        `retry of ${name} returned ${second.status} but original was ${first.status}: ${String(second.body).slice(0, 300)}`,
      );
    }
  }
  return first;
}

function postSurveyPayload(phone) {
  return {
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
    post_qual_l1_ehr_pain_ai_substitution: "[压测] EHR 文书与多系统信息整合最费时，AI 可协助病史摘要与警报过滤。",
    post_qual_l2_human_ai_boundary: "[压测] 行政工作与异常标记可交给 AI；诊断、用药决策与最终责任必须保留给医生。",
    post_qual_l3_system_transformation: "[压测] 医生角色更偏审核；最期待文书负担下降，最担心责任边界模糊。",
    post_phone_last4: phone,
  };
}

const ACTIONS = [
  "send_as_is", "edit_then_send", "send_as_is", "discard_and_rewrite",
  "edit_then_send", "send_as_is", "edit_then_send", "escalate",
];

export default function () {
  // ── session ──
  let r = post("/api/session", {}, "session");
  if (!check(r, { "session 200": (x) => x.status === 200 })) {
    flowCompleted.add(false);
    fail(`session failed: ${r.status}`);
  }
  const s = r.json();
  const sid = s.sessionId;

  // ── pre-survey ──
  r = postMaybeTwice("/api/pre-survey", {
    sessionId: sid,
    answers: {
      pre_specialty: "内科",
      pre_training_level: "主治医师",
      pre_years_post_residency: 5,
      pre_weekly_msg_volume: "1—10 条",
      pre_ai_drafting_familiarity: 3,
    },
  }, "pre-survey");
  check(r, { "pre-survey 200": (x) => x.status === 200 });
  sleep(0.3);

  // ── practice case ──
  r = http.get(`${BASE}/api/case/${s.practiceCaseId}?sessionId=${sid}`, {
    headers, tags: { name: "get-case" },
  });
  check(r, { "practice load 200": (x) => x.status === 200 });
  post("/api/case/open", { sessionId: sid, caseId: s.practiceCaseId, orderIndex: -1 }, "case-open");
  postMaybeTwice("/api/action", {
    sessionId: sid, caseId: s.practiceCaseId, orderIndex: -1, isPractice: true,
    selectedAction: "send_as_is",
    finalReplyText: "[压测] 原样发送",
    caseActionReasonCode: "nothing_to_change",
    quickSurvey: { caseDecisionConfidence: 4, caseDraftHelpfulness: 4 },
    timing: { startedAt: Date.now() - 30000, endedAt: Date.now(), durationMs: 30000 },
  }, "action");
  sleep(0.3);

  // ── 8 formal cases ──
  for (let i = 0; i < s.caseOrder.length; i++) {
    const cid = s.caseOrder[i];
    const action = ACTIONS[i] || "send_as_is";

    r = http.get(`${BASE}/api/case/${cid}?sessionId=${sid}`, {
      headers, tags: { name: "get-case" },
    });
    if (!check(r, { "case load 200": (x) => x.status === 200 })) {
      flowCompleted.add(false);
      fail(`case ${i} load failed: ${r.status}`);
    }

    post("/api/case/open", { sessionId: sid, caseId: cid, orderIndex: i }, "case-open");

    // UI telemetry fires continuously while the participant reads.
    for (const ev of ["case_view_start", "panel_clicked", "action_button_selected"]) {
      post("/api/ui-event", { sessionId: sid, eventType: ev, payload: { caseId: cid } }, "ui-event");
    }

    r = postMaybeTwice("/api/action", {
      sessionId: sid, caseId: cid, orderIndex: i, isPractice: false,
      selectedAction: action,
      finalReplyText: action === "escalate" ? "[escalated]" : `[压测] 第 ${i + 1} 案回复内容。`,
      caseActionReasonCode: action === "escalate" ? "safety_risk" : "basically_ok",
      escalateReason: action === "escalate" ? "[压测] 需要面诊评估" : undefined,
      escalateSubtype: action === "escalate" ? "urgent_evaluation" : undefined,
      quickSurvey: { caseDecisionConfidence: 4, caseDraftHelpfulness: 3 },
      timing: { startedAt: Date.now() - 60000, endedAt: Date.now(), durationMs: 60000 },
    }, "action");
    if (!check(r, { "action 200": (x) => x.status === 200 })) {
      flowCompleted.add(false);
      fail(`case ${i} submit failed: ${r.status} ${String(r.body).slice(0, 200)}`);
    }
    sleep(0.3);
  }

  // ── post-survey ──
  r = postMaybeTwice("/api/post-survey", {
    sessionId: sid,
    payload: postSurveyPayload("9999"),
  }, "post-survey");
  const ok = check(r, {
    "post-survey 200": (x) => x.status === 200,
    "completion code returned": (x) => x.status === 200 && !!x.json().completionCode,
  });
  flowCompleted.add(ok);
  sleep(1);
}
