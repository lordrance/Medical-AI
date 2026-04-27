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

  const r = await fetch(url.toString(), init);
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
