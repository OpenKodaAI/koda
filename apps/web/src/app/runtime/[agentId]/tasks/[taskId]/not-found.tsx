"use client";

import { TerminalSquare } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function RuntimeTaskNotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={TerminalSquare}
        title="Runtime task not found"
        description="The requested runtime task is unavailable or no longer exists."
      />
    </PageSection>
  );
}
