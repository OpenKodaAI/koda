import type { AgentDisplay } from "@/lib/agent-constants";
import { translate } from "@/lib/i18n";

export function resolveAgentSelection(
  selectedBotIds: string[] | undefined,
  availableBotIds: string[],
): string[] {
  if (availableBotIds.length === 0) return [];

  const selectedSet = new Set(selectedBotIds ?? []);
  const resolved = availableBotIds.filter((agentId) => selectedSet.has(agentId));
  return resolved.length > 0 ? resolved : [...availableBotIds];
}

export function toggleAgentSelection(
  selectedBotIds: string[] | undefined,
  agentId: string,
  availableBotIds: string[],
): string[] {
  const current = resolveAgentSelection(selectedBotIds, availableBotIds);
  const next = current.includes(agentId)
    ? current.filter((value) => value !== agentId)
    : [...current, agentId];

  if (next.length === 0 || next.length === availableBotIds.length) {
    return [];
  }

  const nextSet = new Set(next);
  return availableBotIds.filter((value) => nextSet.has(value));
}

export function formatAgentSelectionLabel(
  resolvedBotIds: string[],
  agents: AgentDisplay[],
): string {
  if (
    agents.length === 0 ||
    resolvedBotIds.length === 0 ||
    resolvedBotIds.length === agents.length
  ) {
    return translate("agentSwitcher.allAgents");
  }

  if (resolvedBotIds.length === 1) {
    const matchedAgent = agents.find((agent) => agent.id === resolvedBotIds[0]);
    return matchedAgent?.label ?? resolvedBotIds[0];
  }

  return translate("agentSwitcher.agentsSelected", { count: resolvedBotIds.length });
}
