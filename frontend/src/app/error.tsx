"use client";

// Route-level error boundary. Catches render/runtime exceptions thrown by any
// page (and hydration errors) and shows a recoverable UI instead of Next's
// bare "Application error" white screen. Critical for a research study on
// flaky cross-border mobile networks where a transient error must not become
// an unrecoverable dead-end that makes participants give up.
//
// ★ 中文：页面级的「错误兜底」。
//
// 文件名必须叫 error.tsx 且放在 app/ 下——这是 Next.js 的约定，
// 它会自动把这个组件套在所有页面外面。任何页面渲染时抛异常，
// 都会显示这一屏而不是 Next 默认的白屏 "Application error"。
//
// 为什么关键：白屏 = 死胡同，医生只能关掉页面走人。给个「重试」按钮，
// 大部分临时性错误（网络抖动、代码块加载失败）点一下就恢复了。
//
// 另有 global-error.tsx 兜住更外层的错误（连布局都渲染失败时）。

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  // 这两个参数由 Next.js 自动传进来
  error: Error & { digest?: string };  // 出了什么错
  reset: () => void;                   // 调用它 = 重新渲染这个页面
}) {
  useEffect(() => {
    // Surface to the console for field debugging; never throws.
    // 中文：打到浏览器控制台。医生反馈问题时，如果能让他截个控制台的图，
    // 这行日志就是唯一的线索（前端错误不会自动上报到服务器）。
    // eslint-disable-next-line no-console
    console.error("page_error_boundary", error);
  }, [error]);

  return (
    <div className="card card-section text-center">
      <h2 className="text-lg font-semibold">页面遇到问题</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        请点击「重试」继续；如果仍不行，请点「刷新页面」。您的进度已尽量保留。
      </p>
      <div className="mt-5 flex justify-center gap-3">
        <button className="btn-primary" onClick={() => reset()}>
          重试
        </button>
        <button
          className="rounded-md border border-border px-4 py-2 text-sm"
          onClick={() => window.location.reload()}
        >
          刷新页面
        </button>
      </div>
    </div>
  );
}
