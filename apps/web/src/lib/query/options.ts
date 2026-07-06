import type { QueryObserverOptions } from "@tanstack/react-query";

export type QueryTier = "catalog" | "detail" | "live" | "realtime";

const queryTierDefaults = {
  catalog: {
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    retry: 1,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  },
  detail: {
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    retry: 1,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  },
  live: {
    staleTime: 30_000,
    gcTime: 10 * 60_000,
    retry: 1,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
  },
  realtime: {
    staleTime: 5_000,
    gcTime: 5 * 60_000,
    retry: 0,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchIntervalInBackground: false,
  },
} as const satisfies Record<QueryTier, Partial<QueryObserverOptions>>;

export function getTierQueryOptions(tier: QueryTier) {
  return queryTierDefaults[tier];
}
