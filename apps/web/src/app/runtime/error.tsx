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
  const { tl } = useAppI18n();
  return (
    <RouteErrorState
      title={tl("Runtime unavailable")}
      description={error.message || tl("The runtime section could not be loaded.")}
      onRetry={reset}
    />
  );
}
