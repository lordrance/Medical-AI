"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Users,
} from "lucide-react";
import { api } from "@/lib/api/client";
import type { DashboardHealthResponse } from "@/lib/api/types";

interface Props {
  token: string;
}

export default function SystemHealthCard({ token }: Props) {
  const [data, setData] = useState<DashboardHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let initial = true;

    const fetchHealth = async () => {
      if (initial) setLoading(true);
      setError(null);
      try {
        const json = await api<DashboardHealthResponse>(
          "/api/admin/dashboard/health",
          { headers: { "X-Admin-Token": token } },
        );
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) {
          initial = false;
          setLoading(false);
        }
      }
    };

    void fetchHealth();
    const interval = setInterval(fetchHealth, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [token]);

  if (!token) return null;
  if (loading)
    return (
      <div className="card card-section">
        <h3 className="mb-3 text-base font-semibold">系统健康状态</h3>
        <p className="text-sm text-muted-foreground">正在检测系统状态…</p>
      </div>
    );
  if (error)
    return (
      <div className="card card-section">
        <h3 className="mb-3 text-base font-semibold">系统健康状态</h3>
        <p className="text-sm text-destructive">获取状态失败：{error}</p>
      </div>
    );

  const cards = [
    {
      icon: data!.dbConnected ? (
        <CheckCircle className="h-5 w-5 text-green-500" />
      ) : (
        <XCircle className="h-5 w-5 text-destructive" />
      ),
      label: "数据库连接",
      value: data!.dbConnected ? "正常" : "断开",
      ok: data!.dbConnected,
    },
    {
      icon: <Clock className="h-5 w-5 text-blue-500" />,
      label: "服务器时间",
      value: new Date(data!.serverTime).toLocaleString("zh-CN"),
      ok: true,
    },
    {
      icon: (
        <AlertTriangle
          className={`h-5 w-5 ${data!.llmErrors24h > 0 ? "text-orange-500" : "text-green-500"}`}
        />
      ),
      label: "LLM 24h 错误",
      value: `${data!.llmErrors24h} 次`,
      ok: data!.llmErrors24h === 0,
    },
    {
      icon: <Users className="h-5 w-5 text-purple-500" />,
      label: "活跃会话",
      value: `${data!.activeSessions} 个`,
      ok: true,
    },
  ];

  return (
    <div className="card card-section">
      <h3 className="mb-4 text-base font-semibold">系统健康状态</h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {cards.map((c) => (
          <div
            key={c.label}
            className={`flex flex-col items-center gap-2 rounded-lg border p-4 text-center ${
              c.ok
                ? "border-border bg-card"
                : "border-destructive/30 bg-destructive/5"
            }`}
          >
            {c.icon}
            <span className="text-xs text-muted-foreground">{c.label}</span>
            <span
              className={`text-sm font-semibold ${
                c.ok ? "text-foreground" : "text-destructive"
              }`}
            >
              {c.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
