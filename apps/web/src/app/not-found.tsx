"use client";

import { Compass } from "lucide-react";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export default function NotFound() {
  return (
    <PageSection className="min-h-[420px]">
      <PageEmptyState
        icon={Compass}
        title="Page not found"
        description="The page you requested does not exist or is no longer available."
      />
    </PageSection>
  );
}
