"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  getAgentCatalog,
  setAgentCatalog,
  type AgentDisplay,
} from "@/lib/agent-constants";

type AgentCatalogContextValue = {
  agents: AgentDisplay[];
  agentDisplayMap: Record<string, AgentDisplay>;
  mergeAgents: (items: AgentDisplay[]) => void;
};

const AgentCatalogContext = createContext<AgentCatalogContextValue>({
  agents: [],
  agentDisplayMap: {},
  mergeAgents: () => {},
});

function buildAgentDisplayMap(agents: AgentDisplay[]) {
  return Object.fromEntries(agents.map((agent) => [agent.id, agent])) as Record<string, AgentDisplay>;
}

function mergeAgentDisplays(
  current: AgentDisplay[],
  next: AgentDisplay[],
): AgentDisplay[] {
  if (next.length === 0) return current;

  const byId = new Map(current.map((agent) => [agent.id, agent]));
  let changed = false;
  for (const agent of next) {
    const previous = byId.get(agent.id);
    if (
      previous &&
      previous.label === agent.label &&
      previous.color === agent.color &&
      previous.colorRgb === agent.colorRgb
    ) {
      continue;
    }
    byId.set(agent.id, agent);
    changed = true;
  }

  if (!changed && byId.size === current.length) return current;
  return Array.from(byId.values());
}

export function AgentCatalogProvider({
  initialAgents,
  children,
}: {
  initialAgents: AgentDisplay[];
  children: ReactNode;
}) {
  const [agents, setAgents] = useState(() =>
    initialAgents.length > 0 ? initialAgents : getAgentCatalog(),
  );
  setAgentCatalog(agents);

  const mergeAgents = useCallback((items: AgentDisplay[]) => {
    setAgents((current) => mergeAgentDisplays(current, items));
  }, []);

  const value = useMemo(
    () => ({
      agents,
      agentDisplayMap: buildAgentDisplayMap(agents),
      mergeAgents,
    }),
    [agents, mergeAgents]
  );

  return <AgentCatalogContext.Provider value={value}>{children}</AgentCatalogContext.Provider>;
}

export function useAgentCatalog() {
  return useContext(AgentCatalogContext);
}
