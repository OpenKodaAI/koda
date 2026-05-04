"use client";

import { TerminalSquare } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function RuntimeTaskNotFound() {
  const { tl } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={TerminalSquare}
        title={tl("Runtime task not found")}
        description={tl("The requested runtime task is unavailable or no longer exists.")}
      />
    </PageSection>
  );
}
