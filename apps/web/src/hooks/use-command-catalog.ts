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

interface AgentSpecSkill {
  id?: string;
  name?: string;
  instruction?: string;
  content?: string;
  category?: string;
  enabled?: boolean;
}

interface AgentSpecSkillPolicy {
  enabled?: boolean;
  enabled_skills?: string[];
  disabled_skills?: string[];
}

interface AgentSpecResponse {
  custom_skills?: AgentSpecSkill[];
  skill_policy?: AgentSpecSkillPolicy;
}

function skillDescription(skill: AgentSpecSkill): string | undefined {
  const content = skill.content ?? "";
  const whenToUse = /<when_to_use>\s*([\s\S]*?)\s*<\/when_to_use>/i.exec(content);
  const description = whenToUse?.[1] ?? skill.instruction ?? "";
  return description.trim() || undefined;
}

function skillAllowedByPolicy(skillId: string, policy: AgentSpecSkillPolicy | undefined): boolean {
  if (policy?.enabled === false) return false;
  const enabled = Array.isArray(policy?.enabled_skills)
    ? new Set(policy.enabled_skills.map(String).filter(Boolean))
    : new Set<string>();
  if (enabled.size === 0 || !enabled.has(skillId)) return false;
  const disabled = Array.isArray(policy?.disabled_skills)
    ? new Set(policy.disabled_skills.map(String).filter(Boolean))
    : null;
  return !(disabled && disabled.has(skillId));
}

export function skillsFromAgentSpec(body: AgentSpecResponse | null): SkillEntry[] {
  const policy = body?.skill_policy;
  return (body?.custom_skills ?? [])
    .filter((skill) => {
      const skillId = String(skill.id ?? "");
      return Boolean(skill.enabled !== false && skillId && skillAllowedByPolicy(skillId, policy));
    })
    .map((skill) => ({
      id: String(skill.id),
      title: String(skill.name || skill.id),
      description: skillDescription(skill),
      category: skill.category || "skill",
    }));
}

async function fetchSkillsCatalog(agentId: string): Promise<SkillEntry[]> {
  if (!agentId) return [];
  const response = await fetch(`/api/control-plane/agents/${encodeURIComponent(agentId)}/agent-spec`, {
    method: "GET",
    cache: "no-store",
  });
  if (!response.ok) return [];
  const body = (await response.json().catch(() => null)) as AgentSpecResponse | null;
  return skillsFromAgentSpec(body);
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

export function useSkillsCatalog(agentId: string | null | undefined, enabled = true) {
  const query = useControlPlaneQuery<SkillEntry[]>({
    tier: "catalog",
    queryKey: ["command-bar", "skills", agentId ?? "none"],
    enabled: Boolean(enabled && agentId),
    queryFn: () => fetchSkillsCatalog(agentId ?? ""),
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
