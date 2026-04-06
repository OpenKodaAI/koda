import type { QueryObserverOptions } from "@tanstack/react-query";

export type QueryTier = "catalog" | "detail" | "live" | "realtime";

const queryTierDefaults = {
  catalog: {
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  },
  detail: {
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  },
  live: {
    staleTime: 10_000,
    gcTime: 3 * 60_000,
    retry: 1,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  },
  realtime: {
    staleTime: 5_000,
    gcTime: 60_000,
    retry: 0,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  },
} as const satisfies Record<QueryTier, Partial<QueryObserverOptions>>;

export function getTierQueryOptions(tier: QueryTier) {
  return queryTierDefaults[tier];
}
