"use client";

// Safe localStorage helpers for persisting in-progress answers, so a mobile
// WebView reload (Android/HarmonyOS/WeChat X5 aggressively reload pages on
// backgrounding, lock, incoming call, or memory pressure) does not wipe what
// the participant already typed/selected. Every operation is wrapped in
// try/catch so incognito mode or storage-disabled WebViews degrade silently
// instead of crashing the page.

const PREFIX = "medai-draft:";

/** True if localStorage can actually be written and read (not incognito/blocked). */
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

export function saveDraft(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage full / disabled — nothing we can do; keep going in-memory.
  }
}

export function loadDraft<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw == null) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function clearDraft(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // ignore
  }
}
