// Lightweight typed fetch wrapper. Single source of base URL.
// Retries on network errors (TypeError) with exponential backoff.

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

/** Small sleep for exponential backoff between retries. */
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Retry a fetch call up to `retries` times when it fails with a network
 * error (TypeError). Uses exponential backoff. Does NOT retry HTTP errors
 * (4xx / 5xx) — those are business-logic failures.
 */
async function fetchWithRetry(
  url: string,
  init: RequestInit,
  retries: number,
): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      const r = await fetch(url, init);
      return r; // any HTTP status is a valid response — don't retry
    } catch (err) {
      const isNetworkError =
        err instanceof TypeError ||
        (err instanceof Error && err.name === "TypeError");

      if (!isNetworkError || attempt >= retries) throw err;

      // Exponential backoff: 500ms, 1000ms, 2000ms, ...
      await sleep(500 * Math.pow(2, attempt));
    }
  }
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(path, BASE);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
  }
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers ?? {}),
    },
    signal: opts.signal,
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  const r = await fetchWithRetry(url.toString(), init, 2);
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
