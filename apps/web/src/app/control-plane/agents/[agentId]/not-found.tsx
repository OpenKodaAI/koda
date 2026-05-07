"use client";

import { Bot as AgentIcon } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function ControlPlaneAgentNotFound() {
  const { tl } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={AgentIcon}
        title={tl("Agent configuration not found")}
        description={tl("The requested control plane agent could not be found.")}
      />
    </PageSection>
  );
}
