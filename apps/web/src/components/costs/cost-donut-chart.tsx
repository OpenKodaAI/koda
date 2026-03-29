"use client";

import { useMemo, useState } from "react";
import type { CostBreakdownItem } from "@/components/costs/cost-breakdown-card";
import {
  CategoryBarChart,
  type CategoryBarChartItem,
} from "@/components/ui/category-bar-chart";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatCost } from "@/lib/utils";

export type CostDonutMode = "task" | "bot" | "model";

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

const FALLBACK_COLORS = ["#ff4328", "#ff7e2f", "#ffc349", "#ffe068", "#8fe376", "#7ccfff", "#6f7cff"];

function buildChartItems(
  items: CostBreakdownItem[],
  tl: (value: string, options?: Record<string, unknown>) => string
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
      label: tl("Outros"),
      value: overflow.reduce((sum, item) => sum + item.value, 0),
      share: overflow.reduce((sum, item) => sum + item.share, 0),
      color: "rgba(255,255,255,0.28)",
      meta: tl("{{count}} origens consolidadas", { count: overflow.length }),
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
  const { t, tl } = useAppI18n();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const chartItems = useMemo(() => buildChartItems(items, tl), [items, tl]);
  const total = chartItems.reduce((sum, item) => sum + item.value, 0);

  const activeItem =
    chartItems.find((item) => item.id === hoveredId) ??
    chartItems[0] ??
    null;

  return (
    <CategoryBarChart
      className={cn(compact ? "p-4 sm:p-5" : "p-5 sm:p-6", className)}
      heading={t("costs.allocation.title")}
      controls={
        <div className="segmented-control segmented-control--single-row cost-donut-chart__mode-toggle">
          {([
            { value: "task", label: t("costs.page.allocationModes.task", { defaultValue: "By task" }) },
            { value: "bot", label: t("costs.mode.byBot") },
            { value: "model", label: t("costs.mode.byModel") },
          ] as const).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onModeChange?.(option.value)}
              className={cn("segmented-control__option", mode === option.value && "is-active")}
              aria-pressed={mode === option.value}
            >
              {option.label}
            </button>
          ))}
        </div>
      }
      totalLabel={totalLabel}
      totalValue={formatCost(total)}
      deltaLabel={
        activeItem ? (
          <span>
            {t("costs.page.allocationDominant", { defaultValue: "Dominant:" })}{" "}
            <span className="font-medium text-[var(--text-primary)]">{activeItem.label}</span>{" "}
            <span className="text-[rgba(255,255,255,0.5)]">· {activeItem.share.toFixed(1)}%</span>
          </span>
        ) : (
          t("costs.page.noDominantAllocation", { defaultValue: "No dominant concentration" })
        )
      }
      rangeStartLabel={rangeStartLabel}
      rangeEndLabel={rangeEndLabel}
      items={chartItems}
      activeId={hoveredId}
      onActiveChange={setHoveredId}
      footer={
        activeItem
          ? t("costs.page.allocationFooter", {
              defaultValue:
                "{{label}} accounts for {{value}} of the current cut and leads the observed distribution.",
              label: activeItem.label,
              value: formatCost(activeItem.value),
            })
          : t("costs.page.noAllocationData", {
              defaultValue: "Not enough cost to build the distribution in the period.",
            })
      }
    />
  );
}
