"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Download, Sparkles, Loader2 } from "lucide-react";
import { api, getApiBase } from "@/lib/api/client";
import type {
  LlmSummaryResponse,
  SummaryResponse,
} from "@/lib/api/types";
import { zh } from "@/lib/i18n/zh-CN";

const TABLES = [
  { id: "participants", label: "参与者" },
  { id: "sessions", label: "会话" },
  { id: "case_presentations", label: "案例呈现" },
  { id: "actions", label: "动作（含 final reply / edit_distance / gold match / clientStats）" },
  { id: "case_surveys", label: "案例后小题" },
  { id: "post_surveys", label: "后测问卷" },
  { id: "ui_events", label: "UI 事件" },
  { id: "summary", label: "总览（混淆矩阵 + 打分量表）" },
];

export default function AdminPage() {
  return (
    <Suspense fallback={<div className="card card-section text-muted-foreground">{zh.admin.loading}</div>}>
      <AdminInner />
    </Suspense>
  );
}

function AdminInner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [llmText, setLlmText] = useState<string | null>(null);
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmErr, setLlmErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    void api<SummaryResponse>("/api/admin/summary", {
      headers: { "X-Admin-Token": token },
    })
      .then(setSummary)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  if (!token)
    return <div className="card card-section">{zh.admin.needToken}</div>;
  if (error)
    return <div className="card card-section text-destructive">{error}</div>;
  if (!summary)
    return (
      <div className="card card-section text-muted-foreground">
        {zh.admin.loading}
      </div>
    );

  return (
    <div className="space-y-5">
      <div className="card card-section">
        <h2 className="text-lg font-semibold">{zh.admin.title}</h2>
      </div>

      <div className="card card-section">
        <h3 className="text-base font-semibold">{zh.admin.completion}</h3>
        <p className="mt-2 text-sm text-foreground/80">
          {zh.admin.completionLine(
            summary.completion.completed,
            summary.completion.totalParticipants,
          )}{" "}
          ·{" "}
          <span className="text-muted-foreground">
            {(summary.completion.completionRate * 100).toFixed(1)}%
          </span>
        </p>
        <ul className="mt-2 text-sm text-muted-foreground">
          {summary.completion.byCondition.map((b) => (
            <li key={b.condition}>
              {b.condition}: {b.count}
            </li>
          ))}
        </ul>
      </div>

      <ConfusionMatrixView cm={summary.confusionMatrix} />

      <div className="card card-section">
        <h3 className="mb-3 text-base font-semibold">{zh.admin.perCase}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/60 text-muted-foreground">
              <tr>
                {[
                  "案例",
                  "风险",
                  "类型",
                  "标准答案",
                  "n",
                  "命中 gold",
                  "命中 alt",
                  "unsafe send-as-is",
                  "error survival",
                  "appropriate escalation",
                  "平均时长 (ms)",
                  "平均 edit dist",
                ].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.perCase.map((r) => (
                <tr key={r.caseId} className="border-t border-border">
                  <td className="px-2 py-1.5 font-mono">{r.caseId}</td>
                  <td className="px-2 py-1.5">{r.riskLevel}</td>
                  <td className="px-2 py-1.5">
                    {r.defectPresent ? "有缺陷" : "准确"}
                  </td>
                  <td className="px-2 py-1.5">{r.goldActionZh}</td>
                  <td className="px-2 py-1.5">{r.total}</td>
                  <td className="px-2 py-1.5">{r.matchGold}</td>
                  <td className="px-2 py-1.5">{r.matchAlternates}</td>
                  <td className="px-2 py-1.5">{r.unsafeSendAsIs}</td>
                  <td className="px-2 py-1.5">{r.errorSurvival}</td>
                  <td className="px-2 py-1.5">{r.appropriateEscalation}</td>
                  <td className="px-2 py-1.5">
                    {Math.round(r.meanDurationMs)}
                  </td>
                  <td className="px-2 py-1.5">
                    {r.meanEditDistance.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card card-section">
        <h3 className="mb-3 text-base font-semibold">{zh.admin.perParticipant}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/60 text-muted-foreground">
              <tr>
                {[
                  "参与者",
                  "条件",
                  "n",
                  "命中 gold",
                  "准确率",
                  "error survival",
                  "appr. escalation",
                  "平均时长 (ms)",
                  "平均 edit dist",
                ].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.perParticipant.map((r) => (
                <tr key={r.participantId} className="border-t border-border">
                  <td className="px-2 py-1.5 font-mono">
                    {r.participantId.slice(-8)}
                  </td>
                  <td className="px-2 py-1.5">{r.condition}</td>
                  <td className="px-2 py-1.5">{r.total}</td>
                  <td className="px-2 py-1.5">{r.matchGold}</td>
                  <td className="px-2 py-1.5">
                    {(r.accuracy * 100).toFixed(0)}%
                  </td>
                  <td className="px-2 py-1.5">{r.errorSurvivalCount}</td>
                  <td className="px-2 py-1.5">
                    {r.appropriateEscalationCount}
                  </td>
                  <td className="px-2 py-1.5">
                    {Math.round(r.meanDurationMs)}
                  </td>
                  <td className="px-2 py-1.5">
                    {r.meanEditDistance.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card card-section">
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <Sparkles className="h-4 w-4 text-accent" />
          {zh.admin.llmHeading}
        </h3>
        <p className="text-xs text-muted-foreground">
          {zh.admin.llmDisabledHint}
        </p>
        <div className="mt-3">
          <button
            className="btn-primary"
            disabled={llmBusy}
            onClick={async () => {
              setLlmBusy(true);
              setLlmErr(null);
              try {
                const r = await api<LlmSummaryResponse>(
                  "/api/admin/llm/cohort-summary",
                  {
                    method: "POST",
                    headers: { "X-Admin-Token": token },
                    body: {},
                  },
                );
                setLlmText(r.summaryText);
              } catch (e) {
                setLlmErr((e as Error).message);
              } finally {
                setLlmBusy(false);
              }
            }}
          >
            {llmBusy && <Loader2 className="h-4 w-4 animate-spin" />}
            {llmBusy ? zh.admin.llmGenerating : zh.admin.llmGenerateCohort}
          </button>
        </div>
        {llmErr && (
          <p className="mt-2 text-sm text-destructive">
            {zh.admin.llmError}：{llmErr}
          </p>
        )}
        {llmText && (
          <article className="mt-4 whitespace-pre-line rounded-md border border-border bg-muted/40 p-4 text-sm leading-7">
            {llmText}
          </article>
        )}
      </div>

      <div className="card card-section">
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <Download className="h-4 w-4" />
          {zh.admin.download}
        </h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {TABLES.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between rounded-md border border-border p-3"
            >
              <div className="min-w-0 pr-3">
                <p className="truncate text-sm font-medium">{t.label}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {t.id}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <a
                  className="btn-outline text-xs"
                  href={`${getApiBase()}/api/admin/export?token=${encodeURIComponent(token)}&table=${t.id}&format=csv`}
                >
                  {zh.admin.csv}
                </a>
                <a
                  className="btn-outline text-xs"
                  href={`${getApiBase()}/api/admin/export?token=${encodeURIComponent(token)}&table=${t.id}&format=json`}
                >
                  {zh.admin.json}
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConfusionMatrixView({
  cm,
}: {
  cm: SummaryResponse["confusionMatrix"];
}) {
  return (
    <div className="card card-section">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">{zh.admin.confusion}</h3>
        <span className="text-sm text-muted-foreground">
          {zh.admin.accuracy}：
          <strong className="text-foreground">
            {(cm.accuracy * 100).toFixed(1)}%
          </strong>{" "}
          · n = {cm.total}
        </span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        {zh.admin.confusionHint}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="bg-muted px-2 py-1.5 text-left">↓ gold \ → selected</th>
              {cm.actions.map((a, i) => (
                <th key={a} className="bg-muted px-2 py-1.5">
                  {cm.actionsZh[i]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cm.actions.map((gold, gi) => {
              const rowSum = cm.matrix[gi].reduce((s, x) => s + x, 0);
              return (
                <tr key={gold} className="border-t border-border">
                  <th className="bg-muted/40 px-2 py-1.5 text-left font-mono font-normal">
                    {cm.actionsZh[gi]}
                  </th>
                  {cm.matrix[gi].map((v, si) => {
                    const isDiag = gi === si;
                    return (
                      <td
                        key={si}
                        className={`px-2 py-1.5 text-center ${
                          isDiag ? "bg-primary/10 font-semibold" : ""
                        }`}
                      >
                        {v}
                        {rowSum > 0 && (
                          <span className="ml-1 text-muted-foreground">
                            ({((v / rowSum) * 100).toFixed(0)}%)
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
