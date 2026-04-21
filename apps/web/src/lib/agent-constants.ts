/** Client-safe dynamic agent catalog hydrated by the dashboard layout. */

export interface AgentDisplay {
  id: string;
  label: string;
  color: string;
  colorRgb: string;
}

let agentCatalog: AgentDisplay[] = [];

function buildAgentDisplayMap() {
  return Object.fromEntries(agentCatalog.map((agent) => [agent.id, agent])) as Record<string, AgentDisplay>;
}

export function setAgentCatalog(items: AgentDisplay[]) {
  agentCatalog = [...items];
}

export function getAgentCatalog() {
  return agentCatalog;
}

export function getAgentDisplayMap() {
  return buildAgentDisplayMap();
}

export function getAgentDisplay(agentId: string) {
  const map = buildAgentDisplayMap();
  const direct = map[agentId];
  if (direct) return direct;

  const upper = map[agentId.toUpperCase()];
  if (upper) return upper;

  const lower = agentId.toLowerCase();
  return agentCatalog.find((agent) => agent.id.toLowerCase() === lower) ?? null;
}

export function getAgentColor(agentId: string): string {
  return getAgentDisplay(agentId)?.color ?? "#7A8799";
}

export function getAgentChartColor(agentId: string): string {
  return getAgentColor(agentId);
}

export function getAgentLabel(agentId: string): string {
  return getAgentDisplay(agentId)?.label ?? agentId;
}
