import "server-only";

import {
  controlPlaneFetchJson,
  type ControlPlaneRequestError,
} from "@/lib/control-plane";
import {
  buildControlPlaneDashboardPath,
  type DashboardQueryParams,
} from "@/lib/control-plane-dashboard";
import type { QueryTier } from "@/lib/query/options";

type DashboardServerFetchOptions = {
  params?: DashboardQueryParams;
  tier?: QueryTier;
};

function toControlPlaneTier(tier: QueryTier) {
  if (tier === "catalog") {
    return "catalog";
  }

  if (tier === "detail") {
    return "detail";
  }

  return "live";
}

export async function fetchControlPlaneDashboardServerJson<T>(
  pathname: string,
  options: DashboardServerFetchOptions = {},
) {
  const path = buildControlPlaneDashboardPath(pathname, options.params);
  return controlPlaneFetchJson<T>(path, {}, {
    tier: toControlPlaneTier(options.tier ?? "live"),
  });
}

export type { ControlPlaneRequestError };
