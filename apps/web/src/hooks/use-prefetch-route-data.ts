"use client";

import { useCallback, useContext } from "react";
import { QueryClientContext } from "@tanstack/react-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import { getTierQueryOptions } from "@/lib/query/options";
import type { CostInsightsResponse, DLQEntry, ExecutionSummary } from "@/lib/types";

export function usePrefetchRouteData() {
  const queryClient = useContext(QueryClientContext);
  const { language } = useAppI18n();

  return useCallback(
    (href: string) => {
      if (!queryClient) {
        return;
      }

      const prefetchers: Array<Promise<unknown>> = [];

      if (href === "/") {
        prefetchers.push(
          queryClient.prefetchQuery({
            ...getTierQueryOptions("live"),
            queryKey: queryKeys.dashboard.agentStatsSummary(),
            queryFn: () =>
              fetchControlPlaneDashboardJson("/agents/summary", {
                fallbackError: "Unable to prefetch agent stats.",
              }),
          }),
        );
      }

      if (href === "/executions") {
        prefetchers.push(
          queryClient.prefetchQuery({
            ...getTierQueryOptions("live"),
            queryKey: queryKeys.dashboard.executions({ limit: 100, agentIds: [] }),
            queryFn: () =>
              fetchControlPlaneDashboardJson<ExecutionSummary[]>("/executions", {
                params: { limit: 100 },
                fallbackError: "Unable to prefetch executions.",
              }),
          }),
        );
      }

      if (href === "/costs") {
        prefetchers.push(
          queryClient.prefetchQuery({
            ...getTierQueryOptions("detail"),
            queryKey: queryKeys.dashboard.costs({
              period: "30d",
              agentIds: [],
              groupBy: "auto",
              language,
            }),
            queryFn: () =>
              fetchControlPlaneDashboardJson<CostInsightsResponse>("/costs", {
                params: { period: "30d", groupBy: "auto", lang: language },
                fallbackError: "Unable to prefetch costs.",
              }),
          }),
        );
      }

      if (href === "/dlq") {
        prefetchers.push(
          queryClient.prefetchQuery({
            ...getTierQueryOptions("live"),
            queryKey: queryKeys.dashboard.dlq({ agentIds: [], retryFilter: "", limit: 100 }),
            queryFn: () =>
              fetchControlPlaneDashboardJson<DLQEntry[]>("/dlq", {
                params: { limit: 100 },
                fallbackError: "Unable to prefetch DLQ.",
              }),
          }),
        );
      }

      void Promise.allSettled(prefetchers);
    },
    [language, queryClient],
  );
}
