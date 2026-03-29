"use client";

import { Bot } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function ControlPlaneBotNotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={Bot}
        title="Bot configuration not found"
        description="The requested control plane bot could not be found."
      />
    </PageSection>
  );
}
