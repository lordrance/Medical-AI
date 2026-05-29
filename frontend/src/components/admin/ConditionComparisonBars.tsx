"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3 } from "lucide-react";
import type { LogStatsByConditionResponse } from "@/lib/api/types";

// Human-friendly labels for the keys we expect from the backend.
const KEY_LABELS: Record<string, string> = {
  log_case_review_time: "审题时长 (s)",
  log_time_to_first_action: "首次点击 (s)",
  log_edit_actions: "编辑动作次数",
  log_source_panel_open: "源面板展开率",
  log_help_risk_panel: "护栏面板展开率",
  log_toggle_draft_source: "草稿/源切换次数",
  log_verification_clicks: "核查点击次数",
  log_scroll_dwell_draft_section_dwell_sec: "草稿停留 (s)",
};

export function ConditionComparisonBars({
  data,
}: {
  data: LogStatsByConditionResponse;
}) {
  const chartData = data.metrics.map((m) => ({
    label: KEY_LABELS[m.key] ?? m.key,
    plain: round2(m.plain.mean),
    guardrail: round2(m.guardrail.mean),
    plainN: m.plain.n,
    guardrailN: m.guardrail.n,
  }));

  const sampleSummary = data.metrics.length
    ? `plain n=${data.metrics[0].plain.n} · guardrail n=${data.metrics[0].guardrail.n}`
    : "暂无数据";

  return (
    <div className="card card-section">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <BarChart3 className="h-4 w-4 text-accent" />
          条件对比（核心研究信号）
        </h3>
        <span className="text-xs text-muted-foreground">{sampleSummary}</span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        每个 log_* 指标按 condition 求均值。研究假设：guardrail 组在「护栏面板展开率」「核查点击次数」上应明显高于 plain。
      </p>
      {chartData.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无数据。</p>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 8, right: 24, bottom: 8, left: 100 }}
          >
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="label"
              tick={{ fontSize: 11 }}
              width={100}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 6,
                border: "1px solid hsl(var(--border))",
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="plain" name="plain" fill="#94a3b8" />
            <Bar dataKey="guardrail" name="guardrail" fill="#0ea5e9" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
