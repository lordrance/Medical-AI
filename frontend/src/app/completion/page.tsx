"use client";

import { CheckCircle2 } from "lucide-react";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";

export default function CompletionPage() {
  const code = useStudy((s) => s.completionCode);
  const reset = useStudy((s) => s.reset);

  return (
    <div className="card card-section animate-slide-up text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <CheckCircle2 className="h-7 w-7" />
      </div>
      <h2 className="text-2xl font-semibold tracking-tight">
        {zh.completion.title}
      </h2>
      <p className="mt-3 text-foreground/80 leading-7">{zh.completion.body}</p>
      {code && (
        <div className="mt-6">
          <div className="text-xs text-muted-foreground">{zh.completion.code}</div>
          <code className="mt-1.5 inline-block rounded-md border border-border bg-muted px-4 py-2 font-mono text-lg">
            {code}
          </code>
        </div>
      )}
      <div className="mt-8">
        <button className="btn-ghost text-xs" onClick={reset}>
          {zh.completion.reset}
        </button>
      </div>
    </div>
  );
}
