"use client";

/**
 * 完成页 —— 流程的终点，显示完成码。
 *
 * ★ 完成码只存在这台浏览器的 localStorage 里，服务器不会再发第二次。
 * 医生必须把它记下来才能领报酬，所以页面上有明确提示，
 * 「重置」按钮也加了二次确认（曾经它是无确认的，一误触就找不回来了）。
 *
 * 这一页不发任何请求，数据全部来自提交后测时存下来的全局状态。
 */

import { CheckCircle2 } from "lucide-react";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";

export default function CompletionPage() {
  const code = useStudy((s) => s.completionCode);
  const performance = useStudy((s) => s.performance);
  const reset = useStudy((s) => s.reset);
  // 算准确率百分比。★ 必须先判断 total > 0，否则会除以零得到 NaN，
  // 页面上就会显示「准确率 NaN%」。
  const pct =
    performance && performance.total > 0
      ? ((100 * performance.correct) / performance.total).toFixed(1)
      : null;

  return (
    <div className="card card-section animate-slide-up text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <CheckCircle2 className="h-7 w-7" />
      </div>
      <h2 className="text-2xl font-semibold tracking-tight">
        {zh.completion.title}
      </h2>
      <p className="mt-3 text-foreground/80 leading-7">{zh.completion.body}</p>
      {performance && performance.total > 0 && pct != null && (
        <div className="mt-6 rounded-md border border-border bg-muted/30 px-4 py-4 text-left text-sm">
          <h3 className="font-semibold text-foreground">{zh.completion.performanceTitle}</h3>
          <p className="mt-2 text-foreground/85">
            {zh.completion.performanceLine(performance.correct, performance.total, `${pct}%`)}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">{zh.completion.performanceHint}</p>
        </div>
      )}
      {code && (
        <div className="mt-6">
          <div className="text-xs text-muted-foreground">{zh.completion.code}</div>
          <code className="mt-1.5 inline-block rounded-md border border-border bg-muted px-4 py-2 font-mono text-lg">
            {code}
          </code>
          <p className="mt-2 text-xs text-muted-foreground">
            {zh.completion.codeHint}
          </p>
        </div>
      )}
      <div className="mt-8">
        <button
          className="btn-ghost text-xs"
          // The completion code lives only in this browser, and it is what the
          // participant hands back to claim payment. Resetting wipes it with no
          // way to recover, so never do it on a stray tap.
          onClick={() => {
            if (window.confirm(zh.completion.resetConfirm)) reset();
          }}
        >
          {zh.completion.reset}
        </button>
      </div>
    </div>
  );
}
