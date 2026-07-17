"use client";

// Route-level error boundary. Catches render/runtime exceptions thrown by any
// page (and hydration errors) and shows a recoverable UI instead of Next's
// bare "Application error" white screen. Critical for a research study on
// flaky cross-border mobile networks where a transient error must not become
// an unrecoverable dead-end that makes participants give up.

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface to the console for field debugging; never throws.
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
