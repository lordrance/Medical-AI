"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

interface Summary {
  completion: {
    totalParticipants: number;
    completed: number;
    completionRate: number;
    byCondition: { condition: string; count: number }[];
  };
  confusionMatrix: {
    actions: string[];
    matrix: number[][];
    total: number;
    accuracy: number;
  };
  perCase: {
    caseId: string;
    defectPresent: boolean;
    riskLevel: string;
    goldAction: string;
    total: number;
    matchGold: number;
    matchAlternates: number;
    unsafeSendAsIs: number;
    errorSurvival: number;
    appropriateEscalation: number;
    meanDurationMs: number;
    meanEditDistance: number;
  }[];
  perParticipant: {
    participantId: string;
    condition: string;
    total: number;
    matchGold: number;
    accuracy: number;
    errorSurvivalCount: number;
    appropriateEscalationCount: number;
    meanDurationMs: number;
    meanEditDistance: number;
  }[];
}

const TABLES = [
  { id: "participants", label: "Participants" },
  { id: "sessions", label: "Sessions" },
  { id: "case_presentations", label: "Case presentations" },
  { id: "actions", label: "Actions (含 final reply, edit_distance, gold_match)" },
  { id: "case_surveys", label: "Case quick surveys (3-item × case)" },
  { id: "post_surveys", label: "Post-surveys" },
  { id: "ui_events", label: "UI events" },
  { id: "summary", label: "Summary (混淆矩阵 + per case + per participant)" },
];

export default function AdminExportPage() {
  return (
    <Suspense fallback={<div className="card p-6 text-slate-500">Loading...</div>}>
      <AdminExportInner />
    </Suspense>
  );
}

function AdminExportInner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    void fetch(`/api/admin/summary?token=${encodeURIComponent(token)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setSummary)
      .catch((e) => setError((e as Error).message));
  }, [token]);

  if (!token) {
    return (
      <div className="card p-6">
        <h2 className="text-lg font-semibold">Admin Export</h2>
        <p className="mt-2 text-sm text-slate-600">
          Append <code>?token=YOUR_ADMIN_TOKEN</code> to this URL.
        </p>
      </div>
    );
  }
  if (error) {
    return <div className="card p-6 text-red-600">Error: {error}</div>;
  }
  if (!summary) {
    return <div className="card p-6 text-slate-500">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="card p-6">
        <h2 className="text-lg font-semibold">Completion</h2>
        <p className="mt-2 text-sm text-slate-700">
          {summary.completion.completed} / {summary.completion.totalParticipants} completed (
          {(summary.completion.completionRate * 100).toFixed(1)}%)
        </p>
        <ul className="mt-2 text-sm text-slate-600">
          {summary.completion.byCondition.map((b) => (
            <li key={b.condition}>
              {b.condition}: {b.count}
            </li>
          ))}
        </ul>
      </div>

      <ConfusionMatrixView cm={summary.confusionMatrix} />

      <div className="card p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Per case</h2>
          <span className="text-xs text-slate-500">
            unsafe = defective AI 草稿被原样发送；errorSurvival = defective 案例医生未达到 gold 或 alternate
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                {[
                  "case",
                  "risk",
                  "defect",
                  "gold",
                  "n",
                  "match gold",
                  "match alt",
                  "unsafe send-as-is",
                  "error survival",
                  "appr. escalation",
                  "mean dur (ms)",
                  "mean edit dist",
                ].map((h) => (
                  <th key={h} className="px-2 py-1 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.perCase.map((row) => (
                <tr key={row.caseId} className="border-t border-slate-200">
                  <td className="px-2 py-1 font-mono">{row.caseId}</td>
                  <td className="px-2 py-1">{row.riskLevel}</td>
                  <td className="px-2 py-1">
                    {row.defectPresent ? "defective" : "accurate"}
                  </td>
                  <td className="px-2 py-1">{row.goldAction}</td>
                  <td className="px-2 py-1">{row.total}</td>
                  <td className="px-2 py-1">{row.matchGold}</td>
                  <td className="px-2 py-1">{row.matchAlternates}</td>
                  <td className="px-2 py-1">{row.unsafeSendAsIs}</td>
                  <td className="px-2 py-1">{row.errorSurvival}</td>
                  <td className="px-2 py-1">{row.appropriateEscalation}</td>
                  <td className="px-2 py-1">
                    {Math.round(row.meanDurationMs)}
                  </td>
                  <td className="px-2 py-1">
                    {row.meanEditDistance.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card p-6">
        <h2 className="mb-4 text-lg font-semibold">Per participant</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                {[
                  "participant",
                  "condition",
                  "n",
                  "match gold",
                  "accuracy",
                  "error survival",
                  "appr. escalation",
                  "mean dur (ms)",
                  "mean edit dist",
                ].map((h) => (
                  <th key={h} className="px-2 py-1 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.perParticipant.map((row) => (
                <tr key={row.participantId} className="border-t border-slate-200">
                  <td className="px-2 py-1 font-mono">
                    {row.participantId.slice(-8)}
                  </td>
                  <td className="px-2 py-1">{row.condition}</td>
                  <td className="px-2 py-1">{row.total}</td>
                  <td className="px-2 py-1">{row.matchGold}</td>
                  <td className="px-2 py-1">
                    {(row.accuracy * 100).toFixed(0)}%
                  </td>
                  <td className="px-2 py-1">{row.errorSurvivalCount}</td>
                  <td className="px-2 py-1">
                    {row.appropriateEscalationCount}
                  </td>
                  <td className="px-2 py-1">
                    {Math.round(row.meanDurationMs)}
                  </td>
                  <td className="px-2 py-1">
                    {row.meanEditDistance.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card p-6">
        <h2 className="mb-4 text-lg font-semibold">Download data</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {TABLES.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between rounded border border-slate-200 px-3 py-2"
            >
              <div>
                <p className="text-sm font-medium">{t.label}</p>
                <p className="text-xs text-slate-500 font-mono">{t.id}</p>
              </div>
              <div className="flex gap-2">
                <a
                  className="btn-outline text-xs"
                  href={`/api/admin/export?token=${encodeURIComponent(token)}&table=${t.id}&format=csv`}
                >
                  CSV
                </a>
                <a
                  className="btn-outline text-xs"
                  href={`/api/admin/export?token=${encodeURIComponent(token)}&table=${t.id}&format=json`}
                >
                  JSON
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
  cm: Summary["confusionMatrix"];
}) {
  return (
    <div className="card p-6">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Confusion matrix</h2>
        <span className="text-sm text-slate-500">
          accuracy: <strong>{(cm.accuracy * 100).toFixed(1)}%</strong> · n =
          {" "}{cm.total}
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        rows = gold action · cols = clinician action
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="bg-slate-100 px-2 py-1 text-left">↓ gold \ → selected</th>
              {cm.actions.map((a) => (
                <th key={a} className="bg-slate-100 px-2 py-1">
                  {a}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cm.actions.map((gold, gi) => {
              const rowSum = cm.matrix[gi].reduce((s, x) => s + x, 0);
              return (
                <tr key={gold} className="border-t border-slate-200">
                  <th className="bg-slate-50 px-2 py-1 text-left font-mono font-normal">
                    {gold}
                  </th>
                  {cm.matrix[gi].map((v, si) => {
                    const isDiag = gi === si;
                    return (
                      <td
                        key={si}
                        className={`px-2 py-1 text-center ${
                          isDiag ? "bg-emerald-50 font-semibold" : ""
                        }`}
                      >
                        {v}
                        {rowSum > 0 && (
                          <span className="ml-1 text-slate-400">
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
