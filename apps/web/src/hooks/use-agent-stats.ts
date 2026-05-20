"use client";

import { keepPreviousData } from "@tanstack/react-query";
import type { AgentStats } from "@/lib/types";
import { useContentStable } from "@/hooks/use-content-stable";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";

type UseAgentStatsOptions = {
  recentTaskLimit?: number;
};

export function useAgentStats(agentId?: string, options?: UseAgentStatsOptions) {
  const recentTaskLimit = options?.recentTaskLimit ?? 5;
  const query = useControlPlaneQuery<AgentStats[]>({
    tier: "live",
    queryKey: agentId
      ? queryKeys.dashboard.agentStatsDetail(agentId, recentTaskLimit)
      : queryKeys.dashboard.agentStatsSummary(recentTaskLimit),
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
      if (agentId) {
        const item = await fetchControlPlaneDashboardJson<AgentStats>(
          `/agents/${agentId}/stats`,
          {
            signal,
            params: { recentTaskLimit },
            fallbackError: `Erro ao buscar stats: ${agentId}`,
          },
        );
        return [item];
      }

      return fetchControlPlaneDashboardJson<AgentStats[]>("/agents/summary", {
        signal,
        params: { recentTaskLimit },
        fallbackError: "Erro ao buscar stats dos agents",
      });
    },
  });

  // Hold on to the last structurally-equal reference so downstream memos stay stable
  // even if the underlying query object churns identity on refetch.
  const stableQuery = useStableQueryData({
    data: query.data,
    resetKey: `${agentId ?? "summary"}:${recentTaskLimit}`,
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.error,
  });
  const stableStats = useContentStable(stableQuery.data ?? undefined);

  return {
    stats: stableStats,
    loading: stableQuery.initialLoading,
    refreshing: stableQuery.refreshing,
    error: query.error?.message ?? null,
    refresh: query.refetch,
    lastUpdated: query.dataUpdatedAt || null,
  };
}
