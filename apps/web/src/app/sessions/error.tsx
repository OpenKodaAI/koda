"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";

export default function SessionsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="Sessions unavailable"
      description={error.message || "The sessions workspace could not be loaded."}
      onRetry={reset}
    />
  );
}
