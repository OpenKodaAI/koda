"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";

export default function MemoryError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="Memory workspace unavailable"
      description={error.message || "The memory section could not be loaded."}
      onRetry={reset}
    />
  );
}
