"use client";

import { memo, useMemo } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatCost, truncateText } from "@/lib/utils";

export interface CostBreakdownItem {
  id: string;
  label: string;
  value: number;
  share: number;
  meta?: string;
  color?: string;
}

interface CostBreakdownCardProps {
  title: string;
  subtitle?: string;
  items: CostBreakdownItem[];
  emptyLabel?: string;
  className?: string;
}

export const CostBreakdownCard = memo(function CostBreakdownCard({
  title,
  subtitle,
  items,
  emptyLabel,
  className,
}: CostBreakdownCardProps) {
  const { t } = useAppI18n();
  const resolvedEmptyLabel =
    emptyLabel ??
    t("costs.page.emptyBreakdown", {
      defaultValue: "Not enough data in the selected period.",
    });
  const visibleItems = useMemo(() => items.slice(0, 6), [items]);
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[18px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        className
      )}
      style={{
        boxShadow:
          "inset 0 1px 0 color-mix(in srgb, var(--text-primary) 4%, transparent), 0 16px 38px rgba(0,0,0,0.12)",
      }}
    >
      <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
        <div>
          <p className="eyebrow">{title}</p>
          {subtitle ? (
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{subtitle}</p>
          ) : null}
        </div>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          {t("costs.page.itemsCount", { defaultValue: "{{count}} items", count: items.length })}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="flex min-h-[220px] items-center justify-center text-sm text-[var(--text-tertiary)]">
          {resolvedEmptyLabel}
        </div>
      ) : (
        <div className="divide-y divide-[var(--border-subtle)]">
          {visibleItems.map((item, index) => (
            <div key={item.id} className="px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-semibold tabular-nums text-[var(--text-quaternary)]">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: item.color ?? "var(--tone-info-dot)" }}
                    />
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {truncateText(item.label, 34)}
                    </p>
                  </div>
                  <p className="mt-2 pl-[34px] text-[12px] leading-5 text-[var(--text-tertiary)]">
                    {item.meta ??
                      t("costs.page.breakdownDefaultMeta", {
                        defaultValue: "Consolidated share in the selected period",
                      })}
                  </p>
                </div>

                <div className="shrink-0 text-right">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{formatCost(item.value)}</p>
                  <p className="mt-1 text-[12px] tabular-nums text-[var(--text-tertiary)]">
                    {item.share.toFixed(1)}%
                  </p>
                </div>
              </div>

              <div className="mt-3 pl-[34px]">
                <div className="h-[4px] overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--text-primary)_8%,transparent)]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(item.share, 100)}%`,
                      background: `linear-gradient(90deg, ${item.color ?? "var(--tone-info-dot)"} 0%, color-mix(in srgb, ${item.color ?? "var(--tone-info-dot)"} 75%, white 10%) 100%)`,
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
});
