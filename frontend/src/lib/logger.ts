"use client";

import { buildFetchUrl } from "@/lib/api/client";

/** Fire-and-forget UI event logger. UI must never block on it.
 *
 * ★ 中文：行为埋点上报。「发了就不管」——不等返回、不处理错误。
 *
 * 为什么用 sendBeacon 而不是普通 fetch：
 * sendBeacon 是浏览器专为埋点设计的，它把数据交给浏览器后台发送，
 * **即使用户立刻关掉页面或跳转，数据也照样能发出去**。
 * 普通 fetch 在页面卸载时会被直接掐断，"page_blur"、"case_view_end"
 * 这类恰好发生在离开时刻的事件就全丢了。
 *
 * sendBeacon 不可用时降级成 fetch + keepalive（效果类似但兼容性稍差）。
 * 两条路都失败也无所谓——埋点丢一条不影响医生答题。
 */
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
  const url = buildFetchUrl("/api/ui-event");
  try {
    // 首选 sendBeacon。它返回 false 表示浏览器拒收（比如队列满了），
    // 那就往下走 fetch 兜底。
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(url, blob)) return;
    }
  } catch {
    // fall through to fetch
    // 中文：老浏览器可能压根没有 sendBeacon，或者调用时抛异常。
    // 吞掉，走下面的 fetch。
  }
  // keepalive: true 让请求在页面卸载后仍能继续发送。
  // 开头的 void 和结尾的 .catch(() => {}) 都是明确表示「不关心结果」——
  // 没有 catch 的话浏览器控制台会报未处理的 Promise 异常。
  void fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}
