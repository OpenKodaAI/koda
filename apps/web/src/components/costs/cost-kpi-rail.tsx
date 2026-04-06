"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotLabel } from "@/lib/bot-constants";
import type { CostComparison, CostOverview, CostPeakBucket } from "@/lib/types";
import { cn, formatCost } from "@/lib/utils";

interface CostKpiRailProps {
  overview: CostOverview;
  comparison: CostComparison;
  peakBucket: CostPeakBucket | null;
  className?: string;
}

interface MetricTileProps {
  label: string;
  value: string;
  context: string;
  delta?: number | null;
  emphasize?: boolean;
}

function formatDelta(delta: number | null | undefined) {
  if (delta == null || Number.isNaN(delta)) return null;
  const abs = Math.abs(delta);
  return `${delta > 0 ? "+" : delta < 0 ? "-" : ""}${abs.toFixed(abs >= 10 ? 0 : 1)}%`;
}

function MetricTile({ label, value, context, delta, emphasize = false }: MetricTileProps) {
  const deltaLabel = formatDelta(delta);
  const isPositive = (delta ?? 0) > 0;
  const isNegative = (delta ?? 0) < 0;

  return (
    <div className="min-w-0 px-5 py-4 sm:px-6">
      <div className="min-w-0">
        <p className="overflow-hidden text-ellipsis whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
          {label}
        </p>

        <div className="mt-2 flex flex-wrap items-end gap-2">
          <p
            className={cn(
              "min-w-0 whitespace-nowrap leading-none font-semibold tracking-[-0.05em] text-[var(--text-primary)]",
              emphasize ? "text-[1.8rem] sm:text-[1.95rem]" : "text-[1.45rem] sm:text-[1.58rem]"
            )}
          >
            {value}
          </p>

          {deltaLabel ? (
            <span
              className="mb-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-medium"
              style={{
                borderColor: isPositive
                  ? "color-mix(in srgb, var(--tone-warning-border) 58%, transparent)"
                  : isNegative
                    ? "color-mix(in srgb, var(--tone-success-border) 58%, transparent)"
                    : "var(--border-subtle)",
                color: isPositive
                  ? "var(--tone-warning-text)"
                  : isNegative
                    ? "var(--tone-success-text)"
                    : "var(--text-secondary)",
                background: isPositive
                  ? "color-mix(in srgb, var(--tone-warning-bg) 72%, transparent)"
                  : isNegative
                    ? "color-mix(in srgb, var(--tone-success-bg) 72%, transparent)"
                    : "var(--surface-panel-soft)",
              }}
            >
              {isPositive ? <ArrowUpRight className="h-3.5 w-3.5" /> : null}
              {isNegative ? <ArrowDownRight className="h-3.5 w-3.5" /> : null}
              {!isPositive && !isNegative ? <Minus className="h-3.5 w-3.5" /> : null}
              {deltaLabel}
            </span>
          ) : null}
        </div>
      </div>

      <p className="mt-2 line-clamp-2 text-[12px] leading-5 text-[var(--text-tertiary)]">{context}</p>
    </div>
  );
}

export function CostKpiRail({ overview, comparison, peakBucket, className }: CostKpiRailProps) {
  const { t } = useAppI18n();
  const prefersReducedMotion = useReducedMotion();
  const peakContext = peakBucket
    ? `${peakBucket.label} · ${getBotLabel(peakBucket.top_bot ?? "—")} · ${peakBucket.top_model ?? t("costs.page.noDominantModel", { defaultValue: "No dominant model" })}`
    : t("costs.page.noPeak", { defaultValue: "No highlighted peak in the period" });

  const metrics = [
    {
      label: t("costs.kpis.totalPeriod"),
      value: formatCost(overview.total_cost_usd),
      context: t("costs.page.kpiContexts.totalPeriod", {
        defaultValue: "{{queries}} queries · {{executions}} executions",
        queries: overview.total_queries,
        executions: overview.total_executions,
      }),
      delta: comparison.total_delta_pct,
      emphasize: true,
    },
    {
      label: t("costs.kpis.today"),
      value: formatCost(overview.today_cost_usd),
      context:
        comparison.previous_today_cost_usd == null
          ? t("costs.page.kpiContexts.noComparableBase", { defaultValue: "No comparable baseline" })
          : t("costs.page.kpiContexts.previousBase", {
              defaultValue: "Previous base {{value}}",
              value: formatCost(comparison.previous_today_cost_usd),
            }),
      delta: comparison.today_delta_pct,
    },
    {
      label: t("costs.kpis.costPerResolved"),
      value: formatCost(overview.avg_cost_per_resolved_conversation),
      context: t("costs.page.kpiContexts.resolvedConversations", {
        defaultValue: "{{count}} resolved conversations",
        count: overview.resolved_conversations,
      }),
      delta: comparison.avg_cost_per_resolved_delta_pct,
    },
    {
      label: t("costs.kpis.peakBucket"),
      value: peakBucket ? formatCost(peakBucket.cost_usd) : "—",
      context: peakContext,
    },
  ];

  return (
    <section
      className={cn(
        "overflow-hidden rounded-[18px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        className
      )}
      style={{
        boxShadow:
          "inset 0 1px 0 color-mix(in srgb, var(--text-primary) 4%, transparent), 0 18px 46px rgba(0,0,0,0.12)",
      }}
    >
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-3 sm:px-6">
        <p className="eyebrow">{t("costs.page.operationalRail", { defaultValue: "Operational rail" })}</p>
        <p className="text-[11px] text-[var(--text-tertiary)]">
          {t("costs.page.operationalRailHint", { defaultValue: "4 signals from the current cut" })}
        </p>
      </div>

      <div className="grid divide-y divide-[var(--border-subtle)] md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-4">
        {metrics.map((metric, index) => (
          <motion.div
            key={metric.label}
            initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
            animate={prefersReducedMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.24, delay: Math.min(index * 0.04, 0.14) }}
          >
            <MetricTile {...metric} />
          </motion.div>
        ))}
      </div>
    </section>
  );
}
