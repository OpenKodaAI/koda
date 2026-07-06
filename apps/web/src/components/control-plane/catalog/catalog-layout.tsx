"use client";

import { AgentCatalog } from "./agent-catalog";
import type {
  ControlPlaneAgentSummary,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

export function CatalogLayout({
  agents,
  workspaces,
}: {
  agents: ControlPlaneAgentSummary[];
  workspaces: ControlPlaneWorkspaceTree;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 px-3 py-3 sm:px-4 md:px-6">
      <AgentCatalog agents={agents} workspaces={workspaces} />
    </div>
  );
}
