// 100-concurrent-user READ load against the real Shanghai server.
//
//   k6 run tests/load/k6-production-read.js
//
// The point of this one is capacity of the actual 2-core/2GB box + Caddy +
// TLS + the mainland network path, not application logic (k6-full-flow.js
// covers that on a disposable stack). So it deliberately does not write:
// it creates ONE session in setup() and all VUs replay the read path
// through it. GET /api/case is the hottest endpoint in the study — every
// participant loads it 9 times — so that is what gets hammered.
//
// setup() leaves exactly one throwaway participant row behind; delete it
// afterwards (search participants by the session id printed at the end).

import http from "k6/http";
import { check, sleep, fail } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE || "https://medraftlab.com";
const serverErrors = new Counter("server_errors_5xx");

export const options = {
  stages: [
    { duration: "30s", target: 100 },
    { duration: "1m", target: 100 },
    { duration: "15s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    // Generous vs the local run: this crosses the public internet and
    // terminates TLS on a small shared-CPU instance.
    http_req_duration: ["p(95)<3000"],
    server_errors_5xx: ["count==0"],
  },
};

export function setup() {
  const r = http.post(`${BASE}/api/session`, "{}", {
    headers: { "Content-Type": "application/json" },
  });
  if (r.status !== 200) fail(`setup session failed: ${r.status} ${r.body}`);
  const s = r.json();
  console.log(`setup session: ${s.sessionId} (participant ${s.participantId}) — delete after the run`);
  return { sessionId: s.sessionId, caseOrder: s.caseOrder };
}

export default function (data) {
  // Landing page — Next.js through Caddy.
  let r = http.get(`${BASE}/`, { tags: { name: "page" } });
  if (r.status >= 500) serverErrors.add(1);
  check(r, { "page 200": (x) => x.status === 200 });

  // The hot API path.
  const cid = data.caseOrder[Math.floor(Math.random() * data.caseOrder.length)];
  r = http.get(`${BASE}/api/case/${cid}?sessionId=${data.sessionId}`, {
    tags: { name: "get-case" },
  });
  if (r.status >= 500) serverErrors.add(1);
  check(r, {
    "case 200": (x) => x.status === 200,
    "case has aiDraft": (x) => x.status === 200 && !!x.json().case.aiDraft,
  });

  r = http.get(`${BASE}/healthz`, { tags: { name: "healthz" } });
  if (r.status >= 500) serverErrors.add(1);
  check(r, { "healthz 200": (x) => x.status === 200 });

  sleep(1);
}
