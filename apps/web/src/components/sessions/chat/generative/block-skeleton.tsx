"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import type { GenerativeBlockType } from "@/lib/contracts/generative-ui";

export interface BlockSkeletonProps {
  kind: GenerativeBlockType | string;
}

const HEIGHT_BY_KIND: Record<string, string> = {
  ui_card: "min-h-[80px]",
  ui_table: "min-h-[120px]",
  ui_chart: "min-h-[180px]",
  ui_form: "min-h-[160px]",
  ui_callout: "min-h-[64px]",
  ui_choice: "min-h-[100px]",
  ui_steps: "min-h-[120px]",
};

export function BlockSkeleton({ kind }: BlockSkeletonProps) {
  const { t } = useAppI18n();
  const heightClass = HEIGHT_BY_KIND[kind] ?? "min-h-[80px]";

  return (
    <div
      role="status"
      aria-label={t("chat.blocks.streamingLabel", undefined)}
      className={cn(
        "rounded-[var(--radius-panel-sm)] border border-[color:var(--divider-hair)] bg-[var(--panel-soft)] p-4",
        "animate-pulse",
        heightClass,
      )}
    >
      <div className="h-3 w-1/3 rounded bg-[var(--panel-strong)] mb-2" />
      <div className="h-2 w-full rounded bg-[var(--panel-strong)] mb-1.5 opacity-70" />
      <div className="h-2 w-4/5 rounded bg-[var(--panel-strong)] opacity-70" />
    </div>
  );
}
