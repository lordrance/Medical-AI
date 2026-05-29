"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TrendingUp } from "lucide-react";
import type { CompletionTimeseriesPoint } from "@/lib/api/types";

function formatBucket(iso: string): string {
  // "2026-05-29T04:00:00+00:00" → "05-29 04:00"
  try {
    const d = new Date(iso);
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch {
    return iso;
  }
}

export function CompletionTimeseries({
  data,
}: {
  data: CompletionTimeseriesPoint[];
}) {
  const series = data.map((p) => ({
    label: formatBucket(p.ts),
    started: p.started,
    completed: p.completed,
  }));

  return (
    <div className="card card-section">
      <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <TrendingUp className="h-4 w-4 text-accent" />
        会话时间序列（近 7 天 · 小时桶）
      </h3>
      {series.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无数据。</p>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart
            data={series}
            margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 6,
                border: "1px solid hsl(var(--border))",
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="started"
              name="启动"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="completed"
              name="完成"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
