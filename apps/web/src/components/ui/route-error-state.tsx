"use client";

import { AlertTriangle, RotateCw } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function RouteErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  const { t } = useAppI18n();
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
              {t("generated.ui.try_again_ea521c3f")}
            </ActionButton>
          ) : null
        }
      />
    </PageSection>
  );
}
