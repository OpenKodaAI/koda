"use client";

import { useMemo, useState } from "react";
import type { CostBreakdownItem } from "@/components/costs/cost-breakdown-card";
import {
  CategoryBarChart,
  type CategoryBarChartItem,
} from "@/components/ui/category-bar-chart";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatCost } from "@/lib/utils";

export type CostDonutMode = "task" | "agent" | "model";

interface CostDonutChartProps {
  items: CostBreakdownItem[];
  mode: CostDonutMode;
  onModeChange?: (mode: CostDonutMode) => void;
  totalLabel?: string;
  rangeStartLabel?: string;
  rangeEndLabel?: string;
  compact?: boolean;
  className?: string;
}

const FALLBACK_COLORS = [
  "var(--tone-neutral-dot)",
  "var(--tone-info-dot)",
  "var(--tone-success-dot)",
  "var(--tone-warning-dot)",
  "var(--tone-retry-dot)",
  "var(--text-quaternary)",
];

function buildChartItems(
  items: CostBreakdownItem[],
  t: (value: string, options?: Record<string, unknown>) => string
): CategoryBarChartItem[] {
  const sorted = [...items]
    .filter((item) => item.value > 0)
    .sort((left, right) => right.value - left.value);

  const visible = sorted.slice(0, 7).map((item, index) => ({
    id: item.id,
    label: item.label,
    value: item.value,
    share: item.share,
    color: item.color ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length],
    meta: item.meta,
  })) satisfies CategoryBarChartItem[];

  if (sorted.length > 7) {
    const overflow = sorted.slice(7);
    visible.push({
      id: "other",
      label: t("generated.costs.outros_3a86dfb0"),
      value: overflow.reduce((sum, item) => sum + item.value, 0),
      share: overflow.reduce((sum, item) => sum + item.share, 0),
      color: "color-mix(in srgb, var(--text-primary) 28%, transparent)",
      meta: t("generated.costs.count_origens_3478892d", { count: overflow.length }),
    });
  }

  return visible;
}

export function CostDonutChart({
  items,
  mode,
  onModeChange,
  totalLabel = "Share in period",
  rangeStartLabel,
  rangeEndLabel,
  compact = false,
  className,
}: CostDonutChartProps) {
  const { t } = useAppI18n();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const chartItems = useMemo(() => buildChartItems(items, t), [items, t]);
  const total = chartItems.reduce((sum, item) => sum + item.value, 0);

  const activeItem =
    chartItems.find((item) => item.id === hoveredId) ??
    chartItems[0] ??
    null;

  return (
    <CategoryBarChart
      className={cn(compact ? "" : "p-5", className)}
      heading={t("costs.allocation.title")}
      controls={
        <SoftTabs
          items={[
            { id: "task", label: t("costs.page.allocationModes.task", undefined) },
            { id: "agent", label: t("costs.mode.byAgent") },
            { id: "model", label: t("costs.mode.byModel") },
          ]}
          value={mode}
          onChange={(id) => onModeChange?.(id as CostDonutMode)}
          ariaLabel={t("costs.allocation.title")}
        />
      }
      totalLabel={totalLabel}
      totalValue={formatCost(total)}
      deltaLabel={
        activeItem ? (
          <span>
            {t("costs.page.allocationDominant", undefined)}{" "}
            <span className="font-medium text-[var(--text-primary)]">{activeItem.label}</span>{" "}
            <span className="text-[var(--text-tertiary)]">· {activeItem.share.toFixed(1)}%</span>
          </span>
        ) : (
          t("costs.page.noDominantAllocation", undefined)
        )
      }
      rangeStartLabel={rangeStartLabel}
      rangeEndLabel={rangeEndLabel}
      items={chartItems}
      activeId={hoveredId}
      onActiveChange={setHoveredId}
      footer={
        activeItem
          ? t("costs.page.allocationFooter", { label: activeItem.label, value: formatCost(activeItem.value) })
          : undefined
      }
    />
  );
}
