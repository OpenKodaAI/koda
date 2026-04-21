"use client";

import { Bot as AgentIcon } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function AgentNotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={AgentIcon}
        title="Agent not found"
        description="The requested agent is unavailable or does not exist."
      />
    </PageSection>
  );
}
