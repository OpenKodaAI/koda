"use client";

import { Compass } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function NotFound() {
  const { t } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={Compass}
        title={t("generated.routes.page_not_found_948a46d3")}
        description={t("generated.routes.the_page_you_requested_does_not_exist_or_is__ae3dffad")}
      />
    </PageSection>
  );
}
