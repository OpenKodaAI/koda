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
  const { tl } = useAppI18n();
  return (
    <RouteErrorState
      title={tl("Memory workspace unavailable")}
      description={error.message || tl("The memory section could not be loaded.")}
      onRetry={reset}
    />
  );
}
