"use client";

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

export function CostBreakdownCard({
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
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[18px] border border-[rgba(255,255,255,0.06)] bg-[rgba(8,8,9,0.9)]",
        className
      )}
      style={{
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.025), 0 16px 38px rgba(0,0,0,0.18)",
      }}
    >
      <div className="flex items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] px-5 py-4">
        <div>
          <p className="eyebrow">{title}</p>
          {subtitle ? (
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{subtitle}</p>
          ) : null}
        </div>
        <span className="text-[11px] text-[rgba(255,255,255,0.42)]">
          {t("costs.page.itemsCount", { defaultValue: "{{count}} items", count: items.length })}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="flex min-h-[220px] items-center justify-center text-sm text-[var(--text-tertiary)]">
          {resolvedEmptyLabel}
        </div>
      ) : (
        <div className="divide-y divide-[rgba(255,255,255,0.05)]">
          {items.slice(0, 6).map((item, index) => (
            <div key={item.id} className="px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-semibold tabular-nums text-[rgba(255,255,255,0.32)]">
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
                  <p className="mt-2 pl-[34px] text-[12px] leading-5 text-[rgba(255,255,255,0.46)]">
                    {item.meta ??
                      t("costs.page.breakdownDefaultMeta", {
                        defaultValue: "Consolidated share in the selected period",
                      })}
                  </p>
                </div>

                <div className="shrink-0 text-right">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{formatCost(item.value)}</p>
                  <p className="mt-1 text-[12px] tabular-nums text-[rgba(255,255,255,0.42)]">
                    {item.share.toFixed(1)}%
                  </p>
                </div>
              </div>

              <div className="mt-3 pl-[34px]">
                <div className="h-[4px] overflow-hidden rounded-full bg-[rgba(255,255,255,0.05)]">
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
}
