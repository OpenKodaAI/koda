"use client";

import Link from "next/link";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { PageHeader } from "@/components/layout/header";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export function ControlPlaneUnavailable({
  title,
  description,
}: {
  title?: string;
  description: string;
}) {
  const { t } = useAppI18n();
  const resolvedTitle = title ?? t("controlPlane.unavailable.title");
  return (
    <div className="space-y-6">
      <PageHeader title={resolvedTitle} description={description} />

      <PageSection className="p-5 sm:p-6">
        <PageEmptyState
          title={t("controlPlane.unavailable.pageTitle")}
          description={t("controlPlane.unavailable.description")}
          actions={
            <Link
              href="/control-plane"
              className="button-shell button-shell--primary button-shell--sm"
            >
              {t("controlPlane.unavailable.retry")}
            </Link>
          }
        />
      </PageSection>
    </div>
  );
}
