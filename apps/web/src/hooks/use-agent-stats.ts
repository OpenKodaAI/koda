"use client";

import { keepPreviousData } from "@tanstack/react-query";
import type { AgentStats } from "@/lib/types";
import { useContentStable } from "@/hooks/use-content-stable";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";

export function useAgentStats(agentId?: string) {
  const query = useControlPlaneQuery<AgentStats[]>({
    tier: "live",
    queryKey: agentId
      ? queryKeys.dashboard.agentStatsDetail(agentId)
      : queryKeys.dashboard.agentStatsSummary(),
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
            fallbackError: `Erro ao buscar stats: ${agentId}`,
          },
        );
        return [item];
      }

      return fetchControlPlaneDashboardJson<AgentStats[]>("/agents/summary", {
        signal,
        fallbackError: "Erro ao buscar stats dos agents",
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
