"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";

export default function RuntimeError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="Runtime unavailable"
      description={error.message || "The runtime section could not be loaded."}
      onRetry={reset}
    />
  );
}
