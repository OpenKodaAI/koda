"use client";

import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PageSectionHeader } from "@/components/ui/page-primitives";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function RoutinesShell({ children }: { children: ReactNode }) {
  const { t } = useAppI18n();
  const pathname = usePathname();
  const router = useRouter();
  const value = pathname.startsWith("/routines/dlq") ? "dlq" : "schedules";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <PageSectionHeader
          compact
          title={t("routines.title")}
          description={t("routines.description")}
        />
        <SoftTabs
          items={[
            { id: "schedules", label: t("routines.tabs.schedules") },
            { id: "dlq", label: t("routines.tabs.dlq") },
          ]}
          value={value}
          onChange={(id) => router.push(`/routines/${id}`)}
          ariaLabel={t("routines.tabs.ariaLabel")}
        />
      </div>
      {children}
    </div>
  );
}
