"use client";

import { memo, useMemo } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatCost, truncateText } from "@/lib/utils";
import { StatusDot } from "@/components/ui/status-dot";

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
    t("costs.page.emptyBreakdownShort", {
      defaultValue: "No data",
    });
  const visibleItems = useMemo(() => items.slice(0, 5), [items]);
  return (
    <section className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <header className="min-w-0">
        <p className="m-0 truncate font-mono text-[0.625rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          {title}
        </p>
        {subtitle ? (
          <p className="m-0 mt-1 truncate text-[0.75rem] text-[var(--text-tertiary)]">
            {subtitle}
          </p>
        ) : null}
      </header>

      {items.length === 0 ? (
        <div className="flex min-h-[76px] items-center justify-center gap-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          <StatusDot color="var(--text-quaternary)" />
          <span className="truncate">{resolvedEmptyLabel}</span>
        </div>
      ) : (
        <ol className="flex flex-col">
          {visibleItems.map((item, index) => (
            <li
              key={item.id}
              className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-b border-[color:var(--divider-hair)] py-2 last:border-b-0"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="shrink-0 font-mono text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <StatusDot color={item.color ?? "var(--tone-info-dot)"} />
                <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                  {truncateText(item.label, 34)}
                </p>
              </div>

              <div className="shrink-0 text-right">
                <p className="m-0 font-mono text-[0.8125rem] tabular-nums text-[var(--text-primary)]">
                  {formatCost(item.value)}
                </p>
              </div>

              <div className="col-span-2 grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 pl-[34px]">
                <div className="h-px overflow-hidden rounded-full bg-[var(--panel-strong)]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(item.share, 100)}%`,
                      background: item.color ?? "var(--tone-info-dot)",
                    }}
                  />
                </div>
                <span className="font-mono text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
                  {item.share.toFixed(1)}%
                </span>
              </div>

              {item.meta ? (
                <p className="col-span-2 m-0 truncate pl-[34px] text-[0.6875rem] text-[var(--text-quaternary)]">
                  {item.meta}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
});
