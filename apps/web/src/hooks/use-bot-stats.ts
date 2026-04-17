"use client";

import { useMemo } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import type { BotStats } from "@/lib/types";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";

/**
 * Stabilizes a value's identity across renders by content equality.
 * If the new value serializes identically to the last render, the previous
 * reference is preserved. Protects downstream `useMemo` / `React.memo` chains
 * from reference-churn when the backend returns structurally-identical
 * payloads with drifting object identities (which can defeat React Query's
 * structuralSharing for some payload shapes).
 */
function useContentStable<T>(value: T): T {
  const key = value === undefined ? "__undef__" : JSON.stringify(value);
  // `useMemo` with a string key returns the cached value when content matches,
  // giving us a stable reference across polling refetches.
  return useMemo(() => value, [key]); // eslint-disable-line react-hooks/exhaustive-deps
}

export function useBotStats(botId?: string) {
  const query = useControlPlaneQuery<BotStats[]>({
    tier: "live",
    queryKey: botId
      ? queryKeys.dashboard.botStatsDetail(botId)
      : queryKeys.dashboard.botStatsSummary(),
    // Silent background refetches: only re-render subscribers when `data` or `error`
    // actually changes. Combined with `useContentStable` below this makes polling
    // invisible to the render tree when payload content hasn't moved.
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchInterval: (query) => {
      const hasActive = (query.state.data ?? []).some((s) => s.activeTasks > 0);
      return hasActive ? 8_000 : 30_000;
    },
    queryFn: async ({ signal }) => {
      if (botId) {
        const item = await fetchControlPlaneDashboardJson<BotStats>(
          `/agents/${botId}/stats`,
          {
            signal,
            fallbackError: `Erro ao buscar stats: ${botId}`,
          },
        );
        return [item];
      }

      return fetchControlPlaneDashboardJson<BotStats[]>("/agents/summary", {
        signal,
        fallbackError: "Erro ao buscar stats dos bots",
      });
    },
  });

  // Hold on to the last structurally-equal reference so downstream memos stay stable
  // even if the underlying query object churns identity on refetch.
  const stableStats = useContentStable(query.data);

  return {
    stats: stableStats,
    loading: query.isLoading,
    refreshing: false,
    error: query.error?.message ?? null,
    refresh: query.refetch,
    lastUpdated: query.dataUpdatedAt || null,
  };
}
