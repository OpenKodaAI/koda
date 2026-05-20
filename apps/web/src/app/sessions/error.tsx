"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function SessionsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <RouteErrorState
      title={t("generated.routes.sessions_unavailable_2def7e52")}
      description={error.message || t("generated.routes.the_sessions_workspace_could_not_be_loaded_d61f1050")}
      onRetry={reset}
    />
  );
}
