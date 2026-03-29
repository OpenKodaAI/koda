"use client";

import { BotCatalog } from "./bot-catalog";
import type {
  ControlPlaneBotSummary,
  ControlPlaneCoreProviders,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

export function CatalogLayout({
  bots,
  coreProviders,
  workspaces,
}: {
  bots: ControlPlaneBotSummary[];
  coreProviders: ControlPlaneCoreProviders;
  workspaces: ControlPlaneWorkspaceTree;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col px-3 py-3 sm:px-4 md:px-6">
      <BotCatalog bots={bots} coreProviders={coreProviders} workspaces={workspaces} />
    </div>
  );
}
