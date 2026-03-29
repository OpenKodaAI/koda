"use client";

import type { BotStats } from "@/lib/types";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";

export function useBotStats(botId?: string, refreshInterval: number = 10000) {
  const query = useControlPlaneQuery<BotStats[]>({
    tier: "live",
    queryKey: botId
      ? queryKeys.dashboard.botStatsDetail(botId)
      : queryKeys.dashboard.botStatsSummary(),
    refetchInterval: refreshInterval,
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

  return {
    stats: query.data,
    loading: query.isLoading,
    refreshing: query.isFetching && !query.isLoading,
    error: query.error?.message ?? null,
    refresh: query.refetch,
    lastUpdated: query.dataUpdatedAt || null,
  };
}
