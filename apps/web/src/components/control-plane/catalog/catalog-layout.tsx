"use client";

import { BotCatalog } from "./bot-catalog";
import type {
  ControlPlaneBotSummary,
  ControlPlaneCoreProviders,
  GeneralSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

export function CatalogLayout({
  bots,
  coreProviders,
  generalSettings,
  workspaces,
}: {
  bots: ControlPlaneBotSummary[];
  coreProviders: ControlPlaneCoreProviders;
  generalSettings: GeneralSystemSettings | null;
  workspaces: ControlPlaneWorkspaceTree;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 px-3 py-3 sm:px-4 md:px-6">
      <BotCatalog
        bots={bots}
        coreProviders={coreProviders}
        generalSettings={generalSettings}
        workspaces={workspaces}
      />
    </div>
  );
}
