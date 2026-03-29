import type { QueryObserverOptions } from "@tanstack/react-query";

export type QueryTier = "catalog" | "detail" | "live" | "realtime";

const queryTierDefaults = {
  catalog: {
    staleTime: 15_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  },
  detail: {
    staleTime: 5_000,
    gcTime: 2 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  },
  live: {
    staleTime: 0,
    gcTime: 60_000,
    retry: 1,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  },
  realtime: {
    staleTime: 0,
    gcTime: 30_000,
    retry: 0,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  },
} as const satisfies Record<QueryTier, Partial<QueryObserverOptions>>;

export function getTierQueryOptions(tier: QueryTier) {
  return queryTierDefaults[tier];
}
