"use client";

import { MousePointerClick } from "lucide-react";
import type { UiEventFrequencyRow } from "@/lib/api/types";

/**
 * Tailwind-grid heatmap (no chart library) for event_type × split (condition by default).
 * Each cell shows the count; intensity is normalised against the max value in the table.
 */
export function UiEventHeatmap({ data }: { data: UiEventFrequencyRow[] }) {
  // Collect the union of split keys ("plain", "guardrail", possibly "unknown")
  const splitKeys = Array.from(
    new Set(
      data.flatMap((r) => (r.splits ? Object.keys(r.splits) : [])),
    ),
  ).sort();

  // Max for normalisation across the entire grid (excluding totals)
  const maxCount = data.reduce(
    (m, r) =>
      Math.max(
        m,
        ...splitKeys.map((k) => r.splits?.[k] ?? 0),
      ),
    1,
  );

  return (
    <div className="card card-section">
      <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <MousePointerClick className="h-4 w-4 text-accent" />
        UI 事件频次（按 condition 拆分）
      </h3>
      {data.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无 UI 事件。</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="bg-muted px-2 py-1.5 text-left">事件类型</th>
                <th className="bg-muted px-2 py-1.5 text-right">总计</th>
                {splitKeys.map((k) => (
                  <th
                    key={k}
                    className="bg-muted px-2 py-1.5 text-right font-mono"
                  >
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.eventType} className="border-t border-border">
                  <td className="px-2 py-1.5 font-mono">{r.eventType}</td>
                  <td className="px-2 py-1.5 text-right font-medium">
                    {r.count}
                  </td>
                  {splitKeys.map((k) => {
                    const v = r.splits?.[k] ?? 0;
                    const opacity = v === 0 ? 0 : 0.15 + (v / maxCount) * 0.85;
                    return (
                      <td
                        key={k}
                        className="px-2 py-1.5 text-right tabular-nums"
                        style={{
                          backgroundColor: `rgba(14, 165, 233, ${opacity})`,
                        }}
                      >
                        {v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
