"use client";

// Global error boundary — the ONLY thing that can catch an error thrown by the
// root layout itself. Must render its own <html>/<body>. Uses inline styles so
// it works even if the app stylesheet failed to load. Chinese, with a reload
// button so a crashed shell is still recoverable on participants' phones.

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-Hans">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f8fafc",
          color: "#0f172a",
          padding: "24px",
        }}
      >
        <div style={{ maxWidth: 420, textAlign: "center" }}>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>系统遇到问题</h2>
          <p style={{ marginTop: 8, fontSize: 14, color: "#64748b" }}>
            请点击下方按钮刷新页面继续。若反复出现，请稍后再试。
          </p>
          <div style={{ marginTop: 20, display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              onClick={() => reset()}
              style={{
                background: "#0d9488",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                padding: "10px 20px",
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                background: "#fff",
                color: "#0f172a",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                padding: "10px 20px",
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
