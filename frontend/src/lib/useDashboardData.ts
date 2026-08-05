"use client";

/**
 * 管理后台看板的数据获取逻辑。
 *
 * 这是一个「自定义 Hook」—— React 里把可复用的状态逻辑抽出来的方式。
 * 界面组件只要写 `const { data, loading, refresh } = useDashboardData(token)`，
 * 拉数据、轮询、取消、错误处理全都在这里面处理好了。
 *
 * 只在 /admin 页面用，医生端完全用不到。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { DashboardOverviewResponse } from "@/lib/api/types";

// 自动刷新的间隔。15 秒足够「实时」了，再快只是白白增加服务器负担。
const POLL_INTERVAL_MS = 15_000;

interface DashboardState {
  data: DashboardOverviewResponse | null;
  lastFetchedAt: Date | null;
  loading: boolean;
  error: string | null;
  autoRefresh: boolean;
}

export interface UseDashboardDataReturn extends DashboardState {
  refresh: () => Promise<void>;
  setAutoRefresh: (next: boolean) => void;
}

/**
 * Fetches /api/admin/dashboard/overview once on mount and (optionally) every
 * POLL_INTERVAL_MS. Manual refresh + auto-refresh toggle are the only knobs.
 * No SWR / React Query — useEffect + AbortController is enough at admin scale.
 */
export function useDashboardData(token: string): UseDashboardDataReturn {
  const [state, setState] = useState<DashboardState>({
    data: null,
    lastFetchedAt: null,
    loading: false,
    error: null,
    autoRefresh: false,
  });
  // 存着「上一次请求的取消开关」，用来在发新请求前取消旧的。
  const abortRef = useRef<AbortController | null>(null);

  const doFetch = useCallback(async () => {
    if (!token) return;  // 还没登录就别发请求
    // ★ 先取消上一次还没回来的请求。不取消的话，你连点两次刷新，
    // 两个请求的返回顺序不确定，可能后发的先回、旧数据反而盖掉新数据。
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const d = await api<DashboardOverviewResponse>(
        "/api/admin/dashboard/overview",
        {
          headers: { "X-Admin-Token": token },
          signal: ac.signal,
        },
      );
      if (ac.signal.aborted) return;
      setState((s) => ({
        ...s,
        data: d,
        lastFetchedAt: new Date(),
        loading: false,
        error: null,
      }));
    } catch (e) {
      // 是我们自己取消的（发了新请求）→ 不是错误，静默忽略，
      // 否则界面会闪一下红色错误提示。
      if ((e as { name?: string }).name === "AbortError") return;
      setState((s) => ({
        ...s,
        loading: false,
        error: (e as Error).message,
      }));
    }
  }, [token]);

  // initial fetch
  // 中文：页面打开时拉一次。返回的清理函数在组件卸载时取消未完成的请求
  //（不取消的话，请求回来时组件已经没了，React 会警告内存泄漏）。
  useEffect(() => {
    void doFetch();
    return () => {
      abortRef.current?.abort();
    };
  }, [doFetch]);

  // polling
  // 中文：开了自动刷新才启动定时器。清理函数负责关掉定时器——
  // 不关的话每次开关一下就多一个定时器，越点越快。
  useEffect(() => {
    if (!state.autoRefresh || !token) return;
    const id = setInterval(() => {
      void doFetch();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [state.autoRefresh, token, doFetch]);

  return {
    ...state,
    refresh: doFetch,
    setAutoRefresh: (next: boolean) =>
      setState((s) => ({ ...s, autoRefresh: next })),
  };
}
