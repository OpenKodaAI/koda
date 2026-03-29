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
        "flex h-full w-full flex-col gap-0 rounded-[18px] border-[rgba(255,255,255,0.06)] bg-[rgba(8,8,9,0.88)] p-5 shadow-none",
        className
      )}
      style={{
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 44px rgba(0,0,0,0.2)",
      }}
      {...props}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-[rgba(255,255,255,0.06)] p-0 pb-4">
        <CardTitle className="text-base font-medium text-[var(--text-secondary)]">{heading}</CardTitle>
        {controls ? <div className="shrink-0">{controls}</div> : null}
      </CardHeader>

      <CardContent className="flex flex-col gap-4 p-0 pt-4">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,255,255,0.35)]">
              {totalLabel}
            </p>
            <div className="mt-1 text-[1.85rem] font-semibold leading-none tracking-[-0.05em] text-[var(--text-primary)]">
              {totalValue}
            </div>
          </div>
          {deltaLabel ? <div className="pb-1 text-sm text-[var(--text-secondary)]">{deltaLabel}</div> : null}
        </div>

        {startLabel || endLabel ? (
          <div className="flex items-baseline justify-between gap-3 text-xs text-[rgba(255,255,255,0.42)]">
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
                          active ? "ring-1 ring-white/20" : ""
                        )}
                        style={{
                          background: `linear-gradient(135deg, ${item.color} 0%, color-mix(in srgb, ${item.color} 75%, white 12%) 100%)`,
                          boxShadow: active ? `0 10px 24px color-mix(in srgb, ${item.color} 28%, transparent)` : "none",
                        }}
                      />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent sideOffset={6} className="border-[rgba(255,255,255,0.08)] bg-[rgba(17,18,20,0.84)] text-white">
                    <p className="text-xs text-[rgba(255,255,255,0.72)]">
                      {item.label} ·{" "}
                      <span className="font-medium tracking-[-0.01em] text-white">
                        {item.share.toFixed(1)}%
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-[rgba(255,255,255,0.6)]">
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
            <Separator className="bg-[rgba(255,255,255,0.06)]" />
            <p className="text-xs leading-5 text-[rgba(255,255,255,0.48)]">{footer}</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
