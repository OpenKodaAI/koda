"use client";

import { useCallback, useContext } from "react";
import { QueryClientContext } from "@tanstack/react-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import {
  DASHBOARD_CACHE_GC_MS,
  DASHBOARD_CACHE_STALE_MS,
  DASHBOARD_PAGE_SIZE,
  normalizePaginatedListResponse,
  type PaginatedListResponse,
} from "@/lib/pagination";
import { queryKeys } from "@/lib/query/keys";
import { getTierQueryOptions } from "@/lib/query/options";
import type { CostInsightsResponse, CronJob, DLQEntry, ExecutionSummary, SessionSummary } from "@/lib/types";

const paginatedPrefetchOptions = {
  staleTime: DASHBOARD_CACHE_STALE_MS,
  gcTime: DASHBOARD_CACHE_GC_MS,
  retry: 1,
  refetchOnWindowFocus: false,
} as const;

function getNextPageOffset<T>(lastPage: PaginatedListResponse<T>) {
  return lastPage.page.has_more ? lastPage.page.next_offset : undefined;
}

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
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.agentStatsSummary(0),
            queryFn: () =>
              fetchControlPlaneDashboardJson("/agents/summary", {
                params: { recentTaskLimit: 0 },
                fallbackError: "Unable to prefetch agent stats.",
              }),
          }),
          queryClient.prefetchQuery({
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.executions({
              agentIds: [],
              limit: 10,
              status: "",
              search: "",
            }),
            queryFn: async () =>
              normalizePaginatedListResponse<ExecutionSummary>(
                await fetchControlPlaneDashboardJson<PaginatedListResponse<ExecutionSummary> | ExecutionSummary[]>(
                  "/executions",
                  {
                    params: { paged: 1, limit: 10, offset: 0 },
                    fallbackError: "Unable to prefetch recent executions.",
                  },
                ),
                10,
                0,
              ),
          }),
        );
      }

      if (href === "/executions") {
        prefetchers.push(
          queryClient.prefetchInfiniteQuery({
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.executionPages({
              agentIds: [],
              status: "",
              search: "",
              limit: DASHBOARD_PAGE_SIZE,
            }),
            initialPageParam: 0,
            getNextPageParam: getNextPageOffset,
            queryFn: async ({ pageParam }) => {
              const offset = typeof pageParam === "number" ? pageParam : 0;
              const page = normalizePaginatedListResponse<ExecutionSummary>(
                await fetchControlPlaneDashboardJson<PaginatedListResponse<ExecutionSummary> | ExecutionSummary[]>(
                  "/executions",
                  {
                    params: { paged: 1, limit: DASHBOARD_PAGE_SIZE, offset },
                    fallbackError: "Unable to prefetch executions.",
                  },
                ),
                DASHBOARD_PAGE_SIZE,
                offset,
              );
              return {
                ...page,
                unavailable: false,
              };
            },
          }),
        );
      }

      if (href === "/executions/dlq") {
        prefetchers.push(
          queryClient.prefetchInfiniteQuery({
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.dlqPages({
              agentIds: [],
              retryFilter: "",
              limit: DASHBOARD_PAGE_SIZE,
            }),
            initialPageParam: 0,
            getNextPageParam: getNextPageOffset,
            queryFn: async ({ pageParam }) => {
              const offset = typeof pageParam === "number" ? pageParam : 0;
              const page = normalizePaginatedListResponse<DLQEntry>(
                await fetchControlPlaneDashboardJson<PaginatedListResponse<DLQEntry> | DLQEntry[]>(
                  "/dlq",
                  {
                    params: { paged: 1, limit: DASHBOARD_PAGE_SIZE, offset },
                    fallbackError: "Unable to prefetch DLQ.",
                  },
                ),
                DASHBOARD_PAGE_SIZE,
                offset,
              );
              return {
                ...page,
                unavailable: false,
              };
            },
          }),
        );
      }

      if (href === "/sessions") {
        prefetchers.push(
          queryClient.prefetchInfiniteQuery({
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.sessionPages({
              agentIds: [],
              search: "",
              limit: DASHBOARD_PAGE_SIZE,
            }),
            initialPageParam: 0,
            getNextPageParam: getNextPageOffset,
            queryFn: async ({ pageParam }) => {
              const offset = typeof pageParam === "number" ? pageParam : 0;
              const page = normalizePaginatedListResponse<SessionSummary>(
                await fetchControlPlaneDashboardJson<PaginatedListResponse<SessionSummary> | SessionSummary[]>(
                  "/sessions",
                  {
                    params: { paged: 1, limit: DASHBOARD_PAGE_SIZE, offset },
                    fallbackError: "Unable to prefetch sessions.",
                  },
                ),
                DASHBOARD_PAGE_SIZE,
                offset,
              );
              return {
                ...page,
                unavailable: false,
              };
            },
          }),
        );
      }

      if (href === "/routines/schedules") {
        prefetchers.push(
          queryClient.prefetchInfiniteQuery({
            ...paginatedPrefetchOptions,
            queryKey: queryKeys.dashboard.routineSchedulePages({
              agentIds: [],
              limit: DASHBOARD_PAGE_SIZE,
            }),
            initialPageParam: 0,
            getNextPageParam: getNextPageOffset,
            queryFn: async ({ pageParam }) => {
              const offset = typeof pageParam === "number" ? pageParam : 0;
              const page = normalizePaginatedListResponse<CronJob>(
                await fetchControlPlaneDashboardJson<PaginatedListResponse<CronJob> | CronJob[]>(
                  "/schedules",
                  {
                    params: { paged: 1, limit: DASHBOARD_PAGE_SIZE, offset },
                    fallbackError: "Unable to prefetch schedules.",
                  },
                ),
                DASHBOARD_PAGE_SIZE,
                offset,
              );
              return {
                ...page,
                unavailable: false,
              };
            },
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

      void Promise.allSettled(prefetchers);
    },
    [language, queryClient],
  );
}
