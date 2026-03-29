"use client";

import { Bot } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function BotNotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={Bot}
        title="Bot not found"
        description="The requested bot is unavailable or does not exist."
      />
    </PageSection>
  );
}
