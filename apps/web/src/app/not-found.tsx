"use client";

import { Compass } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function NotFound() {
  const { tl } = useAppI18n();
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={Compass}
        title={tl("Page not found")}
        description={tl("The page you requested does not exist or is no longer available.")}
      />
    </PageSection>
  );
}
