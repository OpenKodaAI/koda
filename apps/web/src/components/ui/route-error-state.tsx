"use client";

import { ErrorState } from "@/components/ui/async-feedback";
import { PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export interface RouteErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Builds a Next.js `error.tsx` boundary. Every boundary renders the shared
 * ErrorState and differs only in its title and fallback description keys.
 */
export function createRouteErrorBoundary(titleKey: string, descriptionKey: string) {
  function RouteErrorBoundary({ error, reset }: RouteErrorBoundaryProps) {
    const { t } = useAppI18n();
    return (
      <PageSection className="min-h-[420px]">
        <ErrorState
          title={t(titleKey)}
          description={error.message || t(descriptionKey)}
          onRetry={reset}
        />
      </PageSection>
    );
  }
  return RouteErrorBoundary;
}
