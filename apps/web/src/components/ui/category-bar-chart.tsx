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
  const { t, language } = useAppI18n();
  const startLabel = renderPeriodLabel(rangeStartLabel, language);
  const endLabel = renderPeriodLabel(rangeEndLabel, language);

  return (
    <Card
      className={cn(
        "flex h-full w-full flex-col gap-0 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] p-3 shadow-none",
        className,
      )}
      {...props}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-[var(--divider-hair)] p-0 pb-2.5">
        <CardTitle className="truncate text-[var(--font-size-sm)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
          {heading}
        </CardTitle>
        {controls ? <div className="shrink-0">{controls}</div> : null}
      </CardHeader>

      <CardContent className="flex flex-col gap-2.5 p-0 pt-2.5">
        <div className="flex min-w-0 flex-wrap items-end gap-x-3 gap-y-1">
          <div className="min-w-0">
            <p className="truncate font-mono text-[0.625rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {totalLabel}
            </p>
            <div className="mt-1 truncate font-mono text-[1.25rem] font-medium leading-none tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {totalValue}
            </div>
          </div>
          {deltaLabel ? (
            <div className="min-w-0 truncate pb-0.5 text-[0.75rem] text-[var(--text-secondary)]">
              {deltaLabel}
            </div>
          ) : null}
        </div>

        {startLabel || endLabel ? (
          <div className="flex items-baseline justify-between gap-3 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
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
                      className="h-6 rounded-[3px] transition-opacity focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]"
                      style={{
                        width: `${shareWidth}%`,
                        opacity: activeId && !active ? 0.45 : 1,
                      }}
                      onMouseEnter={() => onActiveChange?.(item.id)}
                      onMouseLeave={() => onActiveChange?.(null)}
                      onFocus={() => onActiveChange?.(item.id)}
                      onBlur={() => onActiveChange?.(null)}
                    >
                      <div
                        className={cn(
                          "h-full rounded-[3px] transition-colors",
                          active ? "ring-1 ring-[var(--border-strong)]" : ""
                        )}
                        style={{
                          background: item.color,
                        }}
                      />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent
                    sideOffset={6}
                    className="border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-primary)]"
                  >
                    <p className="truncate text-xs text-[var(--text-secondary)]">
                      {item.label} ·{" "}
                      <span className="font-medium tracking-[-0.01em] text-[var(--text-primary)]">
                        {item.share.toFixed(1)}%
                      </span>
                    </p>
                    <p className="mt-1 truncate text-xs text-[var(--text-tertiary)]">
                      {item.meta ?? t("generated.ui.participacao_no_recorte_340e0c5c")}
                    </p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </TooltipProvider>

        {footer ? (
          <>
            <Separator className="bg-[var(--divider-hair)]" />
            <p className="truncate text-[0.75rem] text-[var(--text-tertiary)]">{footer}</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
