"use client";

import { AlertTriangle, RotateCw } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export function RouteErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={AlertTriangle}
        title={title}
        description={description}
        actions={
          onRetry ? (
            <ActionButton
              type="button"
              variant="secondary"
              size="sm"
              onClick={onRetry}
              leading={<RotateCw className="h-4 w-4" />}
            >
              Try again
            </ActionButton>
          ) : null
        }
      />
    </PageSection>
  );
}
