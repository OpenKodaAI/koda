"use client";

import type { AgentDisplay } from "@/lib/agent-constants";
import { requestJson } from "@/lib/http-client";

export type AgentSummaryLike = {
  id: string;
  display_name?: string | null;
  appearance?: {
    label?: string | null;
    color?: string | null;
    color_rgb?: string | null;
  } | null;
};

export type AgentCatalogPage = {
  items: AgentSummaryLike[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type AgentDisplayPage = Omit<AgentCatalogPage, "items"> & {
  items: AgentDisplay[];
};

export function toAgentDisplay(agent: AgentSummaryLike): AgentDisplay {
  return {
    id: agent.id,
    label: String(agent.appearance?.label || agent.display_name || agent.id),
    color: String(agent.appearance?.color || "#A7ADB4"),
    colorRgb: String(agent.appearance?.color_rgb || "167, 173, 180"),
  };
}

export function mergeAgentLists(
  primary: AgentDisplay[],
  secondary: AgentDisplay[],
): AgentDisplay[] {
  if (secondary.length === 0) return primary;
  const byId = new Map(primary.map((agent) => [agent.id, agent]));
  for (const agent of secondary) {
    byId.set(agent.id, agent);
  }
  return Array.from(byId.values());
}

export async function fetchAgentCatalogPage({
  search,
  offset,
  limit,
}: {
  search: string;
  offset: number;
  limit: number;
}): Promise<AgentDisplayPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search.trim()) params.set("q", search.trim());
  const payload = await requestJson<AgentCatalogPage>(
    `/api/control-plane/agents?${params.toString()}`,
  );
  return {
    ...payload,
    items: payload.items.map(toAgentDisplay),
  };
}
