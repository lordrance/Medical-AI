"use client";

import { Activity, AlertTriangle, Zap } from "lucide-react";
import type { LlmStatsResponse } from "@/lib/api/types";

export function LlmHealthPanel({ data }: { data: LlmStatsResponse }) {
  const totalCalls = data.totals.count;
  const errorRatePct = (data.totals.errorRate * 100).toFixed(1);
  const totalTokens = data.totals.promptTokens + data.totals.completionTokens;
  const maxP95 = data.perPurpose.reduce(
    (m, r) => Math.max(m, r.p95Ms),
    0,
  );

  return (
    <div className="card card-section">
      <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <Activity className="h-4 w-4 text-accent" />
        LLM 健康
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          icon={<Zap className="h-4 w-4 text-blue-500" />}
          label="最大 P95 延迟"
          value={`${(maxP95 / 1000).toFixed(2)}s`}
          subtitle={`覆盖 ${data.perPurpose.length} 种 LLM 调用`}
        />
        <StatCard
          icon={
            <AlertTriangle
              className={`h-4 w-4 ${data.totals.errorRate > 0.05 ? "text-destructive" : "text-emerald-500"}`}
            />
          }
          label="错误率"
          value={`${errorRatePct}%`}
          subtitle={`${data.totals.errors} / ${totalCalls} 调用`}
        />
        <StatCard
          icon={<Activity className="h-4 w-4 text-purple-500" />}
          label="Token 总用量"
          value={totalTokens.toLocaleString()}
          subtitle={`prompt ${data.totals.promptTokens.toLocaleString()} + completion ${data.totals.completionTokens.toLocaleString()}`}
        />
      </div>

      {data.perPurpose.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/60 text-muted-foreground">
              <tr>
                {[
                  "用途",
                  "调用次数",
                  "24h",
                  "错误率",
                  "P50 (ms)",
                  "P95 (ms)",
                  "Prompt tokens",
                  "Completion tokens",
                ].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.perPurpose.map((r) => (
                <tr key={r.purpose} className="border-t border-border">
                  <td className="px-2 py-1.5 font-mono">{r.purpose}</td>
                  <td className="px-2 py-1.5">{r.count}</td>
                  <td className="px-2 py-1.5">{r.count24h}</td>
                  <td
                    className={`px-2 py-1.5 ${
                      r.errorRate > 0.05 ? "text-destructive" : ""
                    }`}
                  >
                    {(r.errorRate * 100).toFixed(1)}%
                  </td>
                  <td className="px-2 py-1.5">{Math.round(r.p50Ms)}</td>
                  <td className="px-2 py-1.5">{Math.round(r.p95Ms)}</td>
                  <td className="px-2 py-1.5">
                    {r.promptTokens.toLocaleString()}
                  </td>
                  <td className="px-2 py-1.5">
                    {r.completionTokens.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  subtitle,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {subtitle && (
        <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div>
      )}
    </div>
  );
}
