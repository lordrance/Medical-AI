"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Download,
  Sparkles,
  Loader2,
  RefreshCcw,
  LogIn,
  LogOut,
  ShieldAlert,
} from "lucide-react";
import { ApiError, api, buildFetchUrl } from "@/lib/api/client";
import type {
  LlmSummaryResponse,
  SummaryResponse,
} from "@/lib/api/types";
import { zh } from "@/lib/i18n/zh-CN";
import { PageBack } from "@/components/PageBack";
import { useDashboardData } from "@/lib/useDashboardData";
import { LlmHealthPanel } from "@/components/admin/LlmHealthPanel";
import { CompletionTimeseries } from "@/components/admin/CompletionTimeseries";
import { OverallBehaviorBars } from "@/components/admin/OverallBehaviorBars";
import { UiEventHeatmap } from "@/components/admin/UiEventHeatmap";
import { ActiveSessionsTable } from "@/components/admin/ActiveSessionsTable";

const ADMIN_TOKEN_STORAGE_KEY = "medai_admin_token";

/**
 * Trigger a file download with X-Admin-Token header. Used by every export
 * link so the token never appears in any URL (history / referer / screenshots).
 *
 * Works for files up to a few hundred MB in practice — full DB dumps in this
 * HCI study are typically <20 MB. For larger payloads you'd want streamed
 * downloads via a pre-signed URL or a one-shot download token.
 */
async function downloadWithToken(
  path: string,
  query: Record<string, string>,
  token: string,
  fallbackFilename: string,
): Promise<void> {
  const fullUrl = buildFetchUrl(path, query);
  const r = await fetch(fullUrl, {
    headers: { "X-Admin-Token": token },
  });
  if (!r.ok) {
    throw new Error(`下载失败 (${r.status})`);
  }
  const blob = await r.blob();
  const cd = r.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  const filename = m ? m[1] : fallbackFilename;
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objUrl);
}

const TABLES = [
  { id: "participants", label: "参与者" },
  { id: "sessions", label: "会话" },
  { id: "case_presentations", label: "案例呈现" },
  { id: "actions", label: "动作（含 final reply / edit_distance / gold match / clientStats）" },
  { id: "case_surveys", label: "案例后小题" },
  { id: "post_surveys", label: "后测问卷" },
  { id: "ui_events", label: "UI 事件" },
  { id: "cases", label: "案例内容（题干）" },
  { id: "order_templates", label: "顺序模板" },
  { id: "llm_calls", label: "LLM 调用审计" },
  { id: "cohort_summaries", label: "队列文本总结" },
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
  const router = useRouter();
  const params = useSearchParams();
  const [token, setToken] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [llmText, setLlmText] = useState<string | null>(null);
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmErr, setLlmErr] = useState<string | null>(null);

  // On mount: read token from sessionStorage. If the URL still carries a
  // legacy ?token=... param, ingest it once and strip it so it doesn't leak
  // via browser history / referer / screenshots.
  useEffect(() => {
    const urlToken = params.get("token");
    if (urlToken) {
      sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, urlToken);
      router.replace("/admin");
      setToken(urlToken);
      setAuthChecked(true);
      return;
    }
    const stored = sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY);
    if (stored) setToken(stored);
    setAuthChecked(true);
  }, [params, router]);

  const logout = useCallback(() => {
    sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    setToken(null);
    setSummary(null);
    setError(null);
  }, []);

  const dashboard = useDashboardData(token ?? "");

  useEffect(() => {
    if (!token) return;
    setError(null);
    void api<SummaryResponse>("/api/admin/summary", {
      headers: { "X-Admin-Token": token },
    })
      .then(setSummary)
      .catch((e) => {
        // 401 means the stored token is wrong — drop it and force re-login
        if (e instanceof ApiError && e.status === 401) {
          sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
          setToken(null);
          setError("登录失败：token 不正确，请重新输入。");
        } else {
          setError((e as Error).message);
        }
      });
  }, [token]);

  if (!authChecked)
    return (
      <div className="card card-section text-muted-foreground">
        {zh.admin.loading}
      </div>
    );

  if (!token) return <AdminLogin onLogin={setToken} hint={error} />;

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
      <PageBack />
      <div className="card card-section flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{zh.admin.title}</h2>
        <button
          className="btn-outline inline-flex items-center gap-1.5 px-3 py-1.5 text-xs"
          onClick={logout}
        >
          <LogOut className="h-3.5 w-3.5" />
          登出
        </button>
      </div>

      {/* ---------------- Real-time research dashboard (Phase B) ---------------- */}
      <div className="card card-section">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold">实时审核 Dashboard</h3>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                className="h-3.5 w-3.5"
                checked={dashboard.autoRefresh}
                onChange={(e) => dashboard.setAutoRefresh(e.target.checked)}
              />
              自动刷新 (15s)
            </label>
            <span>
              {dashboard.lastFetchedAt
                ? `上次更新：${dashboard.lastFetchedAt.toLocaleTimeString()}`
                : "尚未更新"}
            </span>
            <button
              className="btn-outline inline-flex items-center gap-1 px-2 py-1 text-xs"
              onClick={() => void dashboard.refresh()}
              disabled={dashboard.loading}
            >
              <RefreshCcw
                className={`h-3.5 w-3.5 ${
                  dashboard.loading ? "animate-spin" : ""
                }`}
              />
              {dashboard.loading ? "加载中…" : "手动刷新"}
            </button>
          </div>
        </div>
        {dashboard.error && (
          <p className="mt-2 text-sm text-destructive">
            Dashboard 加载失败：{dashboard.error}
          </p>
        )}
      </div>

      {dashboard.data && (
        <>
          <ActiveSessionsTable data={dashboard.data.activeSessions} />
          <LlmHealthPanel data={dashboard.data.llmStats} />
          <OverallBehaviorBars data={dashboard.data.logOverall} />
          <CompletionTimeseries data={dashboard.data.timeseries} />
          <UiEventHeatmap data={dashboard.data.uiEvents} />
        </>
      )}

      {/* ---------------- Existing detailed tables (unchanged) ----------------- */}
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
                  zh.admin.matchGoldOnly,
                  zh.admin.matchAltOnly,
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
                  zh.admin.matchGoldOrAlt,
                  zh.admin.accuracy,
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
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border border-border bg-muted/30 p-4 sm:grid-cols-2">
          <div>
            <p className="text-sm font-medium">{zh.admin.exportFullDb}</p>
            <p className="mt-1 text-xs text-muted-foreground">{zh.admin.exportFullDbHint}</p>
            <button
              className="btn-primary mt-3 inline-flex text-xs"
              onClick={() =>
                void downloadWithToken(
                  "/api/admin/export/full-database",
                  {},
                  token,
                  "medai_full_database.sql",
                ).catch((e) => alert((e as Error).message))
              }
            >
              {zh.admin.exportFullDb}
            </button>
          </div>
          <div>
            <p className="text-sm font-medium">{zh.admin.exportBundle}</p>
            <p className="mt-1 text-xs text-muted-foreground">{zh.admin.exportBundleHint}</p>
            <button
              className="btn-primary mt-3 inline-flex text-xs"
              onClick={() =>
                void downloadWithToken(
                  "/api/admin/export/bundle",
                  {},
                  token,
                  "study_export.zip",
                ).catch((e) => alert((e as Error).message))
              }
            >
              study_export.zip
            </button>
          </div>
        </div>
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
                <button
                  className="btn-outline text-xs"
                  onClick={() =>
                    void downloadWithToken(
                      "/api/admin/export",
                      { table: t.id, format: "csv" },
                      token,
                      `${t.id}.csv`,
                    ).catch((e) => alert((e as Error).message))
                  }
                >
                  {zh.admin.csv}
                </button>
                <button
                  className="btn-outline text-xs"
                  onClick={() =>
                    void downloadWithToken(
                      "/api/admin/export",
                      { table: t.id, format: "json" },
                      token,
                      `${t.id}.json`,
                    ).catch((e) => alert((e as Error).message))
                  }
                >
                  {zh.admin.json}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AdminLogin({
  onLogin,
  hint,
}: {
  onLogin: (t: string) => void;
  hint?: string | null;
}) {
  const [value, setValue] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = value.trim();
    if (!t) return;
    sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, t);
    onLogin(t);
  }

  return (
    <div className="mx-auto max-w-md space-y-5">
      <PageBack />
      <div className="card card-section">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-semibold">管理员登录</h2>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          请输入后端 .env 中配置的 ADMIN_TOKEN。Token 仅保存在当前浏览器标签的
          sessionStorage 中，关闭标签后自动清除，不会出现在 URL / 历史记录里。
        </p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <label className="block text-sm font-medium" htmlFor="admin-token">
            ADMIN_TOKEN
          </label>
          <input
            id="admin-token"
            type="password"
            autoComplete="off"
            autoFocus
            className="input w-full"
            placeholder="输入 token"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          {hint && (
            <p className="text-sm text-destructive">{hint}</p>
          )}
          <button
            type="submit"
            className="btn-primary inline-flex w-full items-center justify-center gap-1.5"
            disabled={!value.trim()}
          >
            <LogIn className="h-4 w-4" />
            登录
          </button>
        </form>
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
