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
  const { tl } = useAppI18n();
  return (
    <RouteErrorState
      title={tl("Control plane unavailable")}
      description={error.message || tl("The control plane section could not be loaded.")}
      onRetry={reset}
    />
  );
}
