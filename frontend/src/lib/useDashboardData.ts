"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { DashboardOverviewResponse } from "@/lib/api/types";

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
  const abortRef = useRef<AbortController | null>(null);

  const doFetch = useCallback(async () => {
    if (!token) return;
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
      if ((e as { name?: string }).name === "AbortError") return;
      setState((s) => ({
        ...s,
        loading: false,
        error: (e as Error).message,
      }));
    }
  }, [token]);

  // initial fetch
  useEffect(() => {
    void doFetch();
    return () => {
      abortRef.current?.abort();
    };
  }, [doFetch]);

  // polling
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
