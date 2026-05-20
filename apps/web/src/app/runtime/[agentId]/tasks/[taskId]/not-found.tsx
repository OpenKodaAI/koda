"use client";

import { TerminalSquare } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function RuntimeTaskNotFound() {
  const { t } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={TerminalSquare}
        title={t("generated.routes.runtime_task_not_found_a37376e7")}
        description={t("generated.routes.the_requested_runtime_task_is_unavailable_or_555ff365")}
      />
    </PageSection>
  );
}
