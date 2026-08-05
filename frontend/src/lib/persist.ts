"use client";

// Safe localStorage helpers for persisting in-progress answers, so a mobile
// WebView reload (Android/HarmonyOS/WeChat X5 aggressively reload pages on
// backgrounding, lock, incoming call, or memory pressure) does not wipe what
// the participant already typed/selected. Every operation is wrapped in
// try/catch so incognito mode or storage-disabled WebViews degrade silently
// instead of crashing the page.
//
// ★ 中文：保存「填了一半的答案」，防止手机刷新丢进度。
//
// 为什么需要：安卓 / 鸿蒙 / 微信内置浏览器在这些情况下会悄悄重新加载页面——
// 切到后台、锁屏、来电话、内存不够。医生写了 200 字的开放题，
// 接个电话回来全没了，人就走了。
//
// 和 store.ts 的分工：
//   store.ts   存「我是谁、做到第几题」（凭证和进度）
//   这个文件   存「这一页填了什么」（还没提交的草稿），提交成功后删掉
//
// ★ 每个函数都用 try/catch 包住：无痕模式、存储被禁用、存储满了，
//   这些情况下 localStorage 会直接抛异常。绝不能让「存草稿失败」
//   把整个页面搞崩——那是本末倒置。

// 加前缀，避免和 store.ts 的键、以及其他网站的数据撞名。
const PREFIX = "medai-draft:";

/** True if localStorage can actually be written and read (not incognito/blocked).
 *
 * 中文：探测 localStorage 到底能不能用。不能只判断它「存在」——
 * 无痕模式下对象存在但一写就抛异常，所以真写一个再删掉来验证。
 */
export function isStorageAvailable(): boolean {
  try {
    if (typeof window === "undefined" || !window.localStorage) return false;
    const k = "__medai_probe__";
    window.localStorage.setItem(k, "1");
    window.localStorage.removeItem(k);
    return true;
  } catch {
    return false;
  }
}

/** 存一份草稿。key 一般是 `pre:${sessionId}` 或 `post:${sessionId}`。 */
export function saveDraft(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage full / disabled — nothing we can do; keep going in-memory.
    // 中文：存不了就算了，答案还在内存里，只要不刷新就没事。
    // 静默失败是故意的：这只是个保险，不该打扰医生。
  }
}

/** 读回草稿。没有、或者内容坏了（JSON 解析失败），都返回 null。 */
export function loadDraft<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw == null) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** 删掉草稿。提交成功后调用，避免旧答案残留到下一次。 */
export function clearDraft(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // ignore
  }
}
