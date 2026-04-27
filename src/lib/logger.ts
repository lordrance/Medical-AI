"use client";

export function logEvent(
  sessionId: string,
  eventType: string,
  payload?: Record<string, unknown>,
  casePresentationId?: string,
) {
  const body = JSON.stringify({
    sessionId,
    eventType,
    payload,
    casePresentationId,
    clientTs: new Date().toISOString(),
  });
  try {
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon("/api/ui-event", blob);
      return;
    }
  } catch {
    // fall through
  }
  void fetch("/api/ui-event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}
