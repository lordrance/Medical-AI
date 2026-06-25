// k6 read-only load test for Medical-AI V4 — no database mutation
//
// Usage:
//   k6 run --vus 10 --duration 60s tests/load/k6-v4-readonly.js
//   k6 run --vus 50 --duration 120s tests/load/k6-v4-readonly.js
//   k6 run --vus 100 --duration 120s tests/load/k6-v4-readonly.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "https://101-32-216-183.nip.io";

// These are real case IDs from the seed data (same for every deployment)
const CASE_IDS = [
  "case_01", "case_02", "case_03", "case_04",
  "case_05", "case_06", "case_07", "case_08",
];

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<3000"],
  },
};

export default function () {
  const headers = { "Content-Type": "application/json" };

  // 1. Health check
  let h = http.get(`${BASE}/healthz`, { headers, tags: { name: "healthz" } });
  check(h, { "healthz 200": (r) => r.status === 200 || r.status === 308 });

  // 2. Home page
  let home = http.get(`${BASE}/`, { headers, tags: { name: "home" } });
  check(home, { "home 200": (r) => r.status === 200 || r.status === 308 });

  // 3. Case pages (hottest path — each doctor loads 8 cases)
  const cid = CASE_IDS[Math.floor(Math.random() * CASE_IDS.length)];
  // Need a real sessionId to load cases, but without creating one we test the 404 path
  // which still exercises the full request pipeline (DB query + response)
  let c = http.get(`${BASE}/api/case/${cid}?sessionId=nonexistent`, { headers, tags: { name: "get-case" } });
  check(c, { "case check": (r) => r.status === 404 });

  // 4. Consent page (static Next.js page)
  let consent = http.get(`${BASE}/consent`, { headers, tags: { name: "consent" } });
  check(consent, { "consent 200": (r) => r.status === 200 });

  // 5. Practice page
  let practice = http.get(`${BASE}/practice`, { headers, tags: { name: "practice" } });
  check(practice, { "practice 200": (r) => r.status === 200 });

  // Simulate doctor reading time
  sleep(Math.random() * 2 + 1);
}
