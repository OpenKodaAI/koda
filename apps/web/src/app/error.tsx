"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="We hit a route error"
      description={error.message || "The page could not be rendered."}
      onRetry={reset}
    />
  );
}
