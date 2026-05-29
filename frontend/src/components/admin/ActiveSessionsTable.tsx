"use client";

import { Users } from "lucide-react";
import type { ActiveSessionRow } from "@/lib/api/types";

function formatElapsed(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    const diffSec = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diffSec < 60) return `${Math.round(diffSec)}s 前`;
    if (diffSec < 3600) return `${Math.round(diffSec / 60)}m 前`;
    return `${Math.round(diffSec / 3600)}h 前`;
  } catch {
    return iso;
  }
}

export function ActiveSessionsTable({
  data,
}: {
  data: ActiveSessionRow[];
}) {
  return (
    <div className="card card-section">
      <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
        <Users className="h-4 w-4 text-accent" />
        在线会话（status ≠ completed）
        <span className="ml-2 inline-flex h-5 min-w-[1.5rem] items-center justify-center rounded-full bg-accent/10 px-2 text-xs font-normal text-accent">
          {data.length}
        </span>
      </h3>
      {data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          暂无活跃会话。所有受试者要么尚未开始，要么已完成。
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/60 text-muted-foreground">
              <tr>
                {[
                  "参与者 (后 8 位)",
                  "条件",
                  "开始时间",
                  "已运行",
                  "最后事件",
                  "事件时间",
                ].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => {
                const stuck = r.lastEventAt
                  ? Date.now() - new Date(r.lastEventAt).getTime() >
                    5 * 60_000
                  : true;
                return (
                  <tr key={r.sessionId} className="border-t border-border">
                    <td className="px-2 py-1.5 font-mono">
                      {r.participantId.slice(-8)}
                    </td>
                    <td className="px-2 py-1.5">
                      {r.condition ?? "—"}
                    </td>
                    <td className="px-2 py-1.5">
                      {r.startedAt
                        ? new Date(r.startedAt).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">
                      {formatElapsed(r.elapsedMs)}
                    </td>
                    <td className="px-2 py-1.5 font-mono">
                      {r.lastEventType ?? "—"}
                    </td>
                    <td
                      className={`px-2 py-1.5 ${stuck ? "text-amber-600" : ""}`}
                    >
                      {formatRelative(r.lastEventAt)}
                      {stuck && r.lastEventAt && (
                        <span className="ml-1 text-xs">⚠ 5min+</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
