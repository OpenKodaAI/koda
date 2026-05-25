"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <RouteErrorState
      title={t("generated.routes.we_hit_a_route_error_e67cad31")}
      description={error.message || t("generated.routes.the_page_could_not_be_rendered_4d58a8d1")}
      onRetry={reset}
    />
  );
}
