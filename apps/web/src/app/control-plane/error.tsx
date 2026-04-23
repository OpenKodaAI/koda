"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";

export default function ControlPlaneError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="Control plane unavailable"
      description={error.message || "The control plane section could not be loaded."}
      onRetry={reset}
    />
  );
}
