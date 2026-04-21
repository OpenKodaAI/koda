"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  getAgentCatalog,
  getAgentDisplayMap,
  setAgentCatalog,
  type AgentDisplay,
} from "@/lib/agent-constants";

type AgentCatalogContextValue = {
  agents: AgentDisplay[];
  agentDisplayMap: Record<string, AgentDisplay>;
};

const AgentCatalogContext = createContext<AgentCatalogContextValue>({
  agents: [],
  agentDisplayMap: {},
});

export function AgentCatalogProvider({
  initialAgents,
  children,
}: {
  initialAgents: AgentDisplay[];
  children: ReactNode;
}) {
  const agents = initialAgents.length > 0 ? initialAgents : getAgentCatalog();
  setAgentCatalog(agents);

  const value = useMemo(
    () => ({
      agents,
      agentDisplayMap: getAgentDisplayMap(),
    }),
    [agents]
  );

  return <AgentCatalogContext.Provider value={value}>{children}</AgentCatalogContext.Provider>;
}

export function useAgentCatalog() {
  return useContext(AgentCatalogContext);
}
