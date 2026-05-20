"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function RuntimeError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <RouteErrorState
      title={t("generated.routes.runtime_unavailable_27ef08e4")}
      description={error.message || t("generated.routes.the_runtime_section_could_not_be_loaded_0bc0b972")}
      onRetry={reset}
    />
  );
}
