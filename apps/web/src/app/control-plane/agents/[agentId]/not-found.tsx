"use client";

import { Bot as AgentIcon } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function ControlPlaneAgentNotFound() {
  const { t } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={AgentIcon}
        title={t("generated.routes.agent_configuration_not_found_7fe07d4b")}
        description={t("generated.routes.the_requested_control_plane_agent_could_not__7a323fa9")}
      />
    </PageSection>
  );
}
