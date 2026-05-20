"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function MemoryError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <RouteErrorState
      title={t("generated.routes.memory_workspace_unavailable_55cf16d1")}
      description={error.message || t("generated.routes.the_memory_section_could_not_be_loaded_5ee3b956")}
      onRetry={reset}
    />
  );
}
