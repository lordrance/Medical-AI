// Lightweight typed fetch wrapper. Single source of base URL.
//
// 中文：全站唯一的网络请求出口。所有调后端的地方都走这里，
// 好处是超时、错误处理、URL 拼接只在一个地方维护。
//
// ★ 这个文件解决的核心问题：手机在弱网/跨境时，TCP 连接会「半死」——
// 连上了但一个字节都不返回。浏览器的 fetch 默认**永远不超时**，
// 结果就是医生盯着转圈的按钮等到放弃。所以这里内建了超时。

// 生产环境是 "/api"（和网页同源，由 Caddy 转发给后端），
// 本地开发是 "http://localhost:8000"（前后端分开跑）。
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface Options {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;  // 调用方自己的取消信号（如组件卸载时取消请求）
  /** Per-request timeout override in ms. Defaults: 15s GET, 25s POST. */
  timeoutMs?: number;
}

/** Thrown when a request exceeds its timeout (distinct from an HTTP error).
 *
 * 中文：专门的超时错误类型。和「服务器返回了错误码」区分开，
 * 因为这两种情况该给用户看的提示不一样（超时可重试，422 重试没用）。
 */
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
  // 中文：判断「服务器已经不认识这个会话了」。
  // 靠 404 + 返回内容里的关键词双重确认，避免把「题目不存在」的 404 也误判。
  // 各页面拿到 true 就调 reset() 清空本地状态、送回 /consent 重新开始。
  return (
    e instanceof ApiError &&
    e.status === 404 &&
    /unknown (session|participant)/i.test(e.body)
  );
}

/** 服务器返回了非 2xx 状态码。status 是状态码，body 是返回的原文。 */
export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    // 截断到 200 字符，防止超长的错误正文把日志刷爆
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

/**
 * 发一个请求，自动解析 JSON，出错抛异常。
 *
 * 用法：`const data = await api<CaseResponse>("/api/case/case_01", {...})`
 * 尖括号里是「我期望返回什么类型」，TypeScript 据此做类型检查。
 */
export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const fullUrl = buildFetchUrl(path, opts.query);
  const method = opts.method ?? "GET";
  // 提交类请求给 25 秒（要写数据库，慢一点正常），读取类 15 秒。
  const timeoutMs = opts.timeoutMs ?? (method === "POST" ? 25000 : 15000);

  // Built-in timeout so a half-dead cross-border TCP connection (connected
  // but never returning bytes — the observed Android/HarmonyOS failure mode)
  // rejects instead of leaving the UI spinning forever. Implemented with a
  // plain AbortController + setTimeout for old-Android-WebView compatibility
  // (AbortSignal.any / AbortSignal.timeout are too new for those browsers).
  // AbortController 是浏览器提供的「取消开关」，把它交给 fetch，
  // 之后调 abort() 就能中断请求。
  const controller = new AbortController();
  // 这个标记用来区分「是我们的超时触发的取消」还是「调用方主动取消的」，
  // 两者在 catch 里都表现为 AbortError，但要给用户看的提示不同。
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  // 把调用方的取消信号也接进来（比如组件卸载时要取消未完成的请求）。
  // 本来 AbortSignal.any() 一行就能合并，但老版本安卓 WebView 不支持，
  // 所以手工监听。
  const onCallerAbort = () => controller.abort();
  if (opts.signal) {
    if (opts.signal.aborted) controller.abort();  // 已经取消了就立即中断
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
      // 非 2xx。把返回正文也读出来，方便判断具体是什么错
      //（比如 isSessionInvalid 就要看正文里有没有 "Unknown session"）。
      const text = await r.text().catch(() => "");
      throw new ApiError(r.status, text);
    }
    if (r.status === 204) return undefined as unknown as T;  // 204 = 成功但无内容
    return (await r.json()) as T;
  } catch (e) {
    // Our timeout fired → surface a clear, retryable TimeoutError.
    // 中文：是我们的定时器触发的取消 → 换成语义清晰的 TimeoutError，
    // 这样页面能提示「请求超时，请重试」而不是一句看不懂的 AbortError。
    if (timedOut && e instanceof DOMException && e.name === "AbortError") {
      throw new TimeoutError();
    }
    throw e; // caller-initiated abort or a genuine network error
  } finally {
    // 无论成功失败都要清理，否则定时器和事件监听会泄漏。
    clearTimeout(timer);
    if (opts.signal) opts.signal.removeEventListener("abort", onCallerAbort);
  }
}

export function getApiBase(): string {
  return BASE;
}
