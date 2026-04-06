"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export type CategoryBarChartItem = {
  id: string;
  label: string;
  value: number;
  share: number;
  color: string;
  meta?: string;
};

type PeriodLabel = React.ReactNode | Date | null | undefined;

export interface CategoryBarChartProps extends React.ComponentProps<"div"> {
  heading: React.ReactNode;
  controls?: React.ReactNode;
  totalValue: React.ReactNode;
  totalLabel?: React.ReactNode;
  deltaLabel?: React.ReactNode;
  rangeStartLabel?: PeriodLabel;
  rangeEndLabel?: PeriodLabel;
  items: CategoryBarChartItem[];
  activeId?: string | null;
  onActiveChange?: (id: string | null) => void;
  footer?: React.ReactNode;
}

function renderPeriodLabel(label: PeriodLabel, language: string) {
  if (label instanceof Date) {
    return new Intl.DateTimeFormat(language, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(label);
  }

  return label ?? null;
}

export function CategoryBarChart({
  className,
  heading,
  controls,
  totalValue,
  totalLabel = "Total",
  deltaLabel,
  rangeStartLabel,
  rangeEndLabel,
  items,
  activeId,
  onActiveChange,
  footer,
  ...props
}: CategoryBarChartProps) {
  const { tl, language } = useAppI18n();
  const startLabel = renderPeriodLabel(rangeStartLabel, language);
  const endLabel = renderPeriodLabel(rangeEndLabel, language);

  return (
    <Card
      className={cn(
        "flex h-full w-full flex-col gap-0 rounded-[18px] border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-none",
        className
      )}
      {...props}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-[var(--border-subtle)] p-0 pb-4">
        <CardTitle className="text-base font-medium text-[var(--text-secondary)]">{heading}</CardTitle>
        {controls ? <div className="shrink-0">{controls}</div> : null}
      </CardHeader>

      <CardContent className="flex flex-col gap-4 p-0 pt-4">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {totalLabel}
            </p>
            <div className="mt-1 text-[1.85rem] font-semibold leading-none tracking-[-0.05em] text-[var(--text-primary)]">
              {totalValue}
            </div>
          </div>
          {deltaLabel ? <div className="pb-1 text-sm text-[var(--text-secondary)]">{deltaLabel}</div> : null}
        </div>

        {startLabel || endLabel ? (
          <div className="flex items-baseline justify-between gap-3 text-xs text-[var(--text-tertiary)]">
            <span className="truncate">{startLabel}</span>
            <span className="truncate text-right">{endLabel}</span>
          </div>
        ) : null}

        <TooltipProvider>
          <div className="flex gap-1">
            {items.map((item) => {
              const active = activeId === item.id;
              const shareWidth = Math.max(item.share, 2.5);

              return (
                <Tooltip key={item.id} delayDuration={0}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="h-[44px] rounded-sm transition-all focus:outline-none"
                      style={{
                        width: `${shareWidth}%`,
                        opacity: activeId && !active ? 0.45 : 1,
                        transform: active ? "translateY(-1px)" : "none",
                      }}
                      onMouseEnter={() => onActiveChange?.(item.id)}
                      onMouseLeave={() => onActiveChange?.(null)}
                      onFocus={() => onActiveChange?.(item.id)}
                      onBlur={() => onActiveChange?.(null)}
                    >
                      <div
                        className={cn(
                          "h-full rounded-sm transition-all",
                          active ? "ring-1 ring-[color-mix(in_srgb,var(--text-primary)_18%,transparent)]" : ""
                        )}
                        style={{
                          background: `linear-gradient(135deg, ${item.color} 0%, color-mix(in srgb, ${item.color} 75%, white 12%) 100%)`,
                        }}
                      />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent
                    sideOffset={6}
                    className="border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-primary)]"
                  >
                    <p className="text-xs text-[var(--text-secondary)]">
                      {item.label} ·{" "}
                      <span className="font-medium tracking-[-0.01em] text-[var(--text-primary)]">
                        {item.share.toFixed(1)}%
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                      {item.meta ?? tl("Participação no recorte")}
                    </p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </TooltipProvider>

        {footer ? (
          <>
            <Separator className="bg-[var(--border-subtle)]" />
            <p className="text-xs leading-5 text-[var(--text-tertiary)]">{footer}</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
