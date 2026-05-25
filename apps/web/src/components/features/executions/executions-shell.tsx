"use client";

import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PageSectionHeader } from "@/components/ui/page-primitives";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function ExecutionsShell({ children }: { children: ReactNode }) {
  const { t } = useAppI18n();
  const pathname = usePathname();
  const router = useRouter();
  const value = pathname.startsWith("/executions/dlq") ? "dlq" : "executions";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <PageSectionHeader
          compact
          title={t("executions.shell.title", undefined)}
          description={t("executions.shell.description", undefined)}
        />
        <SoftTabs
          items={[
            {
              id: "executions",
              label: t("executions.shell.tabs.executions", undefined),
            },
            {
              id: "dlq",
              label: t("executions.shell.tabs.dlq", undefined),
            },
          ]}
          value={value}
          onChange={(id) =>
            router.push(id === "dlq" ? "/executions/dlq" : "/executions")
          }
          ariaLabel={t("executions.shell.tabs.ariaLabel", undefined)}
        />
      </div>
      {children}
    </div>
  );
}
