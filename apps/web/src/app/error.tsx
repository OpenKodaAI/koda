"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { tl } = useAppI18n();
  return (
    <RouteErrorState
      title={tl("We hit a route error")}
      description={error.message || tl("The page could not be rendered.")}
      onRetry={reset}
    />
  );
}
