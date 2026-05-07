"use client";

import type { ReactNode } from "react";
import { PageSectionHeader } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function RoutinesShell({ children }: { children: ReactNode }) {
  const { t } = useAppI18n();

  return (
    <div className="space-y-4">
      <PageSectionHeader
        compact
        title={t("routines.title", { defaultValue: "Routines" })}
        description={t("routines.description", {
          defaultValue:
            "Schedules and recurring jobs by agent. Manage cadence, scope and coverage.",
        })}
      />
      {children}
    </div>
  );
}
