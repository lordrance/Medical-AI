// Lightweight typed fetch wrapper. Single source of base URL.

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface Options {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
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
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers ?? {}),
    },
    signal: opts.signal,
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  const r = await fetch(fullUrl, init);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new ApiError(r.status, text);
  }
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

export function getApiBase(): string {
  return BASE;
}
