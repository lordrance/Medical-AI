// Lightweight typed fetch wrapper. Single source of base URL.

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface Options {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Per-request timeout override in ms. Defaults: 15s GET, 25s POST. */
  timeoutMs?: number;
}

/** Thrown when a request exceeds its timeout (distinct from an HTTP error). */
export class TimeoutError extends Error {
  constructor() {
    super("请求超时，请检查网络后重试");
    this.name = "TimeoutError";
  }
}

/**
 * True when the error means the stored session is no longer valid on the
 * backend (DB reset by a redeploy/migration, session expired, or the
 * participant returned much later). Callers should reset the persisted store
 * and send the participant back to /consent to start fresh — otherwise a
 * "reload" just re-reads the same dead session and 404s forever.
 */
export function isSessionInvalid(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    e.status === 404 &&
    /unknown (session|participant)/i.test(e.body)
  );
}

export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    super(`API ${status}: ${body.slice(0, 200)}`);
  }
}

/**
 * Compose a fetchable URL from a root-relative path + optional query.
 *
 * `BASE` is either:
 *   - an absolute URL like "http://localhost:8000" (dev), in which case
 *     we prefix it onto the path; or
 *   - a relative path like "/api" or "" (prod same-origin deploys behind
 *     Caddy), in which case we leave the path alone and `fetch()` will
 *     use the current page origin automatically. We do NOT pass it to
 *     `new URL(path, base)` because that constructor rejects relative
 *     bases with "Invalid base URL".
 *
 * The path itself is always rooted (e.g. "/api/admin/summary"), so it
 * already carries the /api prefix the backend expects.
 */
export function buildFetchUrl(
  path: string,
  query?: Record<string, string | number | undefined>,
): string {
  let url: string;
  if (/^https?:\/\//.test(BASE)) {
    url = BASE.replace(/\/$/, "") + path;
  } else {
    url = path;
  }
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) params.set(k, String(v));
    }
    const q = params.toString();
    if (q) url += (url.includes("?") ? "&" : "?") + q;
  }
  return url;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const fullUrl = buildFetchUrl(path, opts.query);
  const method = opts.method ?? "GET";
  const timeoutMs = opts.timeoutMs ?? (method === "POST" ? 25000 : 15000);

  // Built-in timeout so a half-dead cross-border TCP connection (connected
  // but never returning bytes — the observed Android/HarmonyOS failure mode)
  // rejects instead of leaving the UI spinning forever. Implemented with a
  // plain AbortController + setTimeout for old-Android-WebView compatibility
  // (AbortSignal.any / AbortSignal.timeout are too new for those browsers).
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const onCallerAbort = () => controller.abort();
  if (opts.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener("abort", onCallerAbort);
  }

  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers ?? {}),
    },
    signal: controller.signal,
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  try {
    const r = await fetch(fullUrl, init);
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new ApiError(r.status, text);
    }
    if (r.status === 204) return undefined as unknown as T;
    return (await r.json()) as T;
  } catch (e) {
    // Our timeout fired → surface a clear, retryable TimeoutError.
    if (timedOut && e instanceof DOMException && e.name === "AbortError") {
      throw new TimeoutError();
    }
    throw e; // caller-initiated abort or a genuine network error
  } finally {
    clearTimeout(timer);
    if (opts.signal) opts.signal.removeEventListener("abort", onCallerAbort);
  }
}

export function getApiBase(): string {
  return BASE;
}
