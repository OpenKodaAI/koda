"use client";

import { Bot as AgentIcon } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function ControlPlaneAgentNotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={AgentIcon}
        title="Agent configuration not found"
        description="The requested control plane agent could not be found."
      />
    </PageSection>
  );
}
