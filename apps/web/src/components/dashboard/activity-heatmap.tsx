"use client";

import { memo, type ReactNode } from "react";
import type { DailyActivityResult } from "@/hooks/use-daily-activity";
import { SoftTabs, type SoftTabItem } from "@/components/ui/soft-tabs";
import { cn } from "@/lib/utils";

export interface ActivityHeatmapStat {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}

interface ActivityHeatmapProps {
  data: DailyActivityResult;
  title?: string;
  subtitle?: string;
  tooltipTemplate?: (cell: { date: string; count: number }) => string;
  className?: string;
  periods?: SoftTabItem[];
  periodValue?: string;
  onPeriodChange?: (id: string) => void;
  stats?: ActivityHeatmapStat[];
  scopeSlot?: ReactNode;
  legend?: { less: string; more: string };
}

const INTENSITY_OPACITY: Record<number, number> = {
  0: 0,
  1: 0.22,
  2: 0.44,
  3: 0.68,
  4: 0.92,
};

const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso: string): string {
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  const year = Number(parts[0]);
  const month = Number(parts[1]) - 1;
  const day = Number(parts[2]);
  if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) return iso;
  return `${MONTH_SHORT[month] ?? ""} ${day}, ${year}`;
}

function ActivityHeatmapComponent({
  data,
  title,
  tooltipTemplate,
  className,
  periods,
  periodValue,
  onPeriodChange,
  stats,
  scopeSlot,
  legend,
}: ActivityHeatmapProps) {
  const { weeks } = data;
  const weeksLength = weeks.length;
  const resolvedLegend = legend ?? { less: "less", more: "more" };
  const gridTemplate = `repeat(${weeksLength}, minmax(0, 28px))`;

  return (
    <section
      aria-label={title ?? "Agent activity"}
      className={cn(
        "relative flex w-full flex-col gap-5",
        className,
      )}
    >
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">{scopeSlot}</div>

        <div className="flex flex-wrap items-center gap-3 sm:justify-end">
          {periods && periods.length > 0 && periodValue ? (
            <SoftTabs
              items={periods}
              value={periodValue}
              onChange={(id) => onPeriodChange?.(id)}
              ariaLabel={title ?? "Activity period"}
            />
          ) : null}
          <div className="hidden items-center gap-1.5 sm:flex">
            <span className="text-[10px] text-[var(--text-quaternary)]">{resolvedLegend.less}</span>
            <div className="flex gap-[3px]">
              {[0, 1, 2, 3, 4].map((step) => (
                <span
                  key={step}
                  className="h-[10px] w-[10px] rounded-[3px] border border-[var(--divider-hair)]"
                  style={{
                    background:
                      step === 0
                        ? "var(--panel-soft)"
                        : `rgba(var(--accent-rgb), ${INTENSITY_OPACITY[step]})`,
                  }}
                />
              ))}
            </div>
            <span className="text-[10px] text-[var(--text-quaternary)]">{resolvedLegend.more}</span>
          </div>
        </div>
      </header>

      {stats && stats.length > 0 ? (
        <div
          className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
          role="group"
          aria-label="Activity summary"
        >
          {stats.map((stat) => (
            <div
              key={String(stat.label)}
              className="flex flex-col gap-0.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5"
            >
              <span className="font-[var(--font-mono)] text-[10.5px] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                {stat.label}
              </span>
              <span className="text-[1.125rem] font-medium leading-[1.15] tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
                {stat.value}
              </span>
              {stat.hint ? (
                <span className="text-[0.6875rem] text-[var(--text-tertiary)]">{stat.hint}</span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex w-full flex-col items-center gap-2">
        {/* Heatmap grid row */}
        <div className="flex">
          <div
            role="grid"
            aria-readonly
            className="grid"
            style={{ gridTemplateColumns: gridTemplate, gap: "5px" }}
          >
            {weeks.map((week, colIdx) => (
              <div key={`col-${colIdx}`} role="row" className="flex flex-col gap-[5px]">
                {week.map((cell, rowIdx) => {
                  const opacity = INTENSITY_OPACITY[cell.intensity] ?? 0;
                  const tooltip = tooltipTemplate
                    ? tooltipTemplate(cell)
                    : cell.count > 0
                      ? `${cell.count} on ${formatDate(cell.date)}`
                      : `${formatDate(cell.date)} — idle`;
                  return (
                    <div
                      key={`${colIdx}-${rowIdx}`}
                      role="gridcell"
                      aria-label={tooltip}
                      title={tooltip}
                      className={cn(
                        "aspect-square w-full rounded-[5px] border border-[var(--divider-hair)]",
                        "transition-[transform,background-color] duration-[160ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        "hover:scale-[1.15] hover:border-[var(--border-strong)]",
                      )}
                      style={{
                        background:
                          opacity === 0
                            ? "var(--panel-soft)"
                            : `rgba(var(--accent-rgb), ${opacity})`,
                      }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function arePropsEqual(prev: ActivityHeatmapProps, next: ActivityHeatmapProps): boolean {
  if (prev.title !== next.title) return false;
  if (prev.subtitle !== next.subtitle) return false;
  if (prev.className !== next.className) return false;
  if (prev.periodValue !== next.periodValue) return false;
  if (prev.onPeriodChange !== next.onPeriodChange) return false;
  if (prev.tooltipTemplate !== next.tooltipTemplate) return false;
  if (prev.scopeSlot !== next.scopeSlot) return false;
  if (prev.periods !== next.periods) return false;
  if (prev.legend !== next.legend) return false;

  // Deep-ish compare for stats by value (small array)
  if (prev.stats?.length !== next.stats?.length) return false;
  if (prev.stats && next.stats) {
    for (let i = 0; i < prev.stats.length; i += 1) {
      const a = prev.stats[i]!;
      const b = next.stats[i]!;
      if (a.label !== b.label || a.value !== b.value || a.hint !== b.hint) return false;
    }
  }

  // Data comparison — inexpensive hash based on totals + cells signature
  const a = prev.data;
  const b = next.data;
  if (a === b) return true;
  if (
    a.totalCount !== b.totalCount ||
    a.totalDays !== b.totalDays ||
    a.maxCount !== b.maxCount ||
    a.maxCost !== b.maxCost ||
    a.cells.length !== b.cells.length
  ) {
    return false;
  }
  // Content equality: shallow scan of counts + dates
  for (let i = 0; i < a.cells.length; i += 1) {
    if (a.cells[i]!.count !== b.cells[i]!.count) return false;
    if (a.cells[i]!.date !== b.cells[i]!.date) return false;
  }
  return true;
}

export const ActivityHeatmap = memo(ActivityHeatmapComponent, arePropsEqual);
