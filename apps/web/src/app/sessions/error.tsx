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
  const { tl } = useAppI18n();
  return (
    <RouteErrorState
      title={tl("Sessions unavailable")}
      description={error.message || tl("The sessions workspace could not be loaded.")}
      onRetry={reset}
    />
  );
}
