"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function ControlPlaneError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <RouteErrorState
      title={t("generated.routes.control_plane_unavailable_ebef0c95")}
      description={error.message || t("generated.routes.the_control_plane_section_could_not_be_loade_8b86eed7")}
      onRetry={reset}
    />
  );
}
