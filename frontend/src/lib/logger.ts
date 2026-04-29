"use client";

import { getApiBase } from "@/lib/api/client";

/** Fire-and-forget UI event logger. UI must never block on it. */
export function logEvent(
  sessionId: string,
  eventType: string,
  payload?: Record<string, unknown>,
  casePresentationId?: string,
): void {
  const body = JSON.stringify({
    sessionId,
    eventType,
    payload,
    casePresentationId,
    clientTs: new Date().toISOString(),
  });
  const url = `${getApiBase()}/api/ui-event`;
  try {
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(url, blob)) return;
    }
  } catch {
    // fall through to fetch
  }
  void fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}
