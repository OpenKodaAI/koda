"use client";

import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import type {
  SkillEntry,
  ToolEntry,
} from "@/components/command-bar/command-registry";
import type { PendingApproval } from "@/lib/contracts/sessions";

interface ListResponse<T> {
  items: T[];
}

async function fetchSkillsCatalog(): Promise<SkillEntry[]> {
  const response = await fetch("/api/control-plane/skills", {
    method: "GET",
    cache: "no-store",
  });
  if (!response.ok) return [];
  const body = (await response.json().catch(() => null)) as ListResponse<SkillEntry> | null;
  return body?.items ?? [];
}

async function fetchToolsCatalog(agentId: string): Promise<ToolEntry[]> {
  if (!agentId) return [];
  const response = await fetchControlPlaneDashboardJson<ListResponse<ToolEntry>>(
    `/agents/${encodeURIComponent(agentId)}/tools`,
    { fallbackError: "Unable to load tools catalog" },
  ).catch(() => null);
  return response?.items ?? [];
}

async function fetchPendingApprovals(
  agentId: string,
): Promise<PendingApproval[]> {
  if (!agentId) return [];
  const response = await fetchControlPlaneDashboardJson<
    ListResponse<PendingApproval>
  >(`/agents/${encodeURIComponent(agentId)}/approvals`, {
    fallbackError: "Unable to load pending approvals",
  }).catch(() => null);
  return response?.items ?? [];
}

export function useSkillsCatalog(enabled = true) {
  const query = useControlPlaneQuery<SkillEntry[]>({
    tier: "catalog",
    queryKey: ["command-bar", "skills"],
    enabled,
    queryFn: fetchSkillsCatalog,
    notifyOnChangeProps: ["data"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });
  return query.data ?? [];
}

export function useToolsCatalog(agentId: string | null | undefined, enabled = true) {
  const query = useControlPlaneQuery<ToolEntry[]>({
    tier: "catalog",
    queryKey: ["command-bar", "tools", agentId ?? "none"],
    enabled: Boolean(enabled && agentId),
    queryFn: () => fetchToolsCatalog(agentId ?? ""),
    notifyOnChangeProps: ["data"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });
  return query.data ?? [];
}

export function usePendingApprovalsCatalog(
  agentId: string | null | undefined,
  enabled = true,
) {
  const query = useControlPlaneQuery<PendingApproval[]>({
    tier: "realtime",
    queryKey: ["command-bar", "approvals", agentId ?? "none"],
    enabled: Boolean(enabled && agentId),
    queryFn: () => fetchPendingApprovals(agentId ?? ""),
    notifyOnChangeProps: ["data"],
    refetchInterval: 15_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });
  return query.data ?? [];
}
