"use client";

import { useMemo } from "react";
import { keepPreviousData, useQueries } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type {
  SquadOverviewItem,
  SquadOverviewResponse,
  SquadThreadSummary,
  SquadThreadsResponse,
} from "@/lib/squads";

export interface RoomEntry {
  thread: SquadThreadSummary;
  squad: SquadOverviewItem;
  /** Sorting key derived from thread updatedAt → createdAt → squad lastActiveAt. */
  sortKey: string | null;
}

interface UseRoomsResult {
  rooms: RoomEntry[];
  squads: SquadOverviewItem[];
  loading: boolean;
  error: Error | null;
  available: boolean;
}

/**
 * Aggregates squad overview + per-squad thread lists into a flat, sorted
 * stream of "rooms" the sessions rail can display alongside single-agent
 * conversations. Each squad is fetched independently so React Query caches
 * the per-squad thread list separately from the overview, keeping
 * invalidations narrow when one room mutates.
 */
export function useRooms(): UseRoomsResult {
  const overviewQuery = useControlPlaneQuery<SquadOverviewResponse>({
    tier: "live",
    queryKey: queryKeys.dashboard.squadsOverview(null),
    refetchInterval: 30_000,
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadOverviewResponse>(
        "/squads/overview",
        {
          signal,
          fallbackError: "Failed to load squads.",
        },
      ),
  });

  const stableOverview = useStableQueryData<SquadOverviewResponse>({
    data: overviewQuery.data,
    resetKey: "dashboard:squads:overview",
    isPending: overviewQuery.isPending,
    isFetching: overviewQuery.isFetching,
    error: overviewQuery.error,
  });

  const squads = useMemo(
    () => stableOverview.data?.items ?? [],
    [stableOverview.data?.items],
  );
  const available = stableOverview.data?.available ?? false;

  const threadsResults = useQueries({
    queries: squads.map((squad) => ({
      queryKey: queryKeys.dashboard.squadThreads(squad.squadId, null),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchControlPlaneDashboardJson<SquadThreadsResponse>(
          `/squads/${squad.squadId}/threads`,
          {
            signal,
            fallbackError: "Failed to load squad threads.",
          },
        ),
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      refetchOnReconnect: false,
      placeholderData: keepPreviousData,
    })),
  });

  const rooms = useMemo<RoomEntry[]>(() => {
    const out: RoomEntry[] = [];
    threadsResults.forEach((result, index) => {
      const squad = squads[index];
      if (!squad || !result.data) return;
      for (const thread of result.data.items) {
        const sortKey =
          thread.updatedAt || thread.createdAt || squad.lastActiveAt || null;
        out.push({ thread, squad, sortKey });
      }
    });
    return out.sort((a, b) => {
      const at = a.sortKey ? new Date(a.sortKey).getTime() : 0;
      const bt = b.sortKey ? new Date(b.sortKey).getTime() : 0;
      return bt - at;
    });
  }, [squads, threadsResults]);

  const loading =
    overviewQuery.isPending ||
    threadsResults.some((result) => result.isPending && squads.length > 0);
  const error =
    (overviewQuery.error as Error | null) ??
    (threadsResults.find((result) => result.error)?.error as Error | null) ??
    null;

  return { rooms, squads, loading, error, available };
}
