"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { PageMetricStrip, PageMetricStripItem } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getAgentLabel } from "@/lib/agent-constants";
import type { CostComparison, CostOverview, CostPeakBucket } from "@/lib/types";
import { cn, formatCost } from "@/lib/utils";

interface CostKpiRailProps {
  overview: CostOverview;
  comparison: CostComparison;
  peakBucket: CostPeakBucket | null;
  className?: string;
}

function formatDelta(delta: number | null | undefined) {
  if (delta == null || Number.isNaN(delta)) return null;
  const abs = Math.abs(delta);
  const sign = delta > 0 ? "+" : delta < 0 ? "-" : "";
  return `${sign}${abs.toFixed(abs >= 10 ? 0 : 1)}%`;
}

function renderDelta(delta: number | null | undefined) {
  const label = formatDelta(delta);
  if (!label) return null;
  const isPositive = (delta ?? 0) > 0;
  const isNegative = (delta ?? 0) < 0;
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{
        color: isPositive
          ? "var(--tone-warning-text)"
          : isNegative
            ? "var(--tone-success-text)"
            : "var(--text-tertiary)",
      }}
    >
      {isPositive ? <ArrowUpRight className="h-3 w-3" strokeWidth={1.75} /> : null}
      {isNegative ? <ArrowDownRight className="h-3 w-3" strokeWidth={1.75} /> : null}
      {label}
    </span>
  );
}

export function CostKpiRail({ overview, comparison, peakBucket, className }: CostKpiRailProps) {
  const { t } = useAppI18n();
  const peakContext = peakBucket
    ? `${peakBucket.label} · ${getAgentLabel(peakBucket.top_bot ?? "—")} · ${peakBucket.top_model ?? t("costs.page.noDominantModel", { defaultValue: "No dominant model" })}`
    : t("costs.page.noPeak", { defaultValue: "No highlighted peak in the period" });

  return (
    <PageMetricStrip className={cn(className)}>
      <PageMetricStripItem
        label={t("costs.kpis.totalPeriod")}
        value={formatCost(overview.total_cost_usd)}
        hint={t("costs.page.kpiContexts.totalPeriod", {
          defaultValue: "{{queries}} queries · {{executions}} executions",
          queries: overview.total_queries,
          executions: overview.total_executions,
        })}
        delta={renderDelta(comparison.total_delta_pct)}
      />
      <PageMetricStripItem
        label={t("costs.kpis.today")}
        value={formatCost(overview.today_cost_usd)}
        hint={
          comparison.previous_today_cost_usd == null
            ? t("costs.page.kpiContexts.noComparableBase", { defaultValue: "No comparable baseline" })
            : t("costs.page.kpiContexts.previousBase", {
                defaultValue: "Previous base {{value}}",
                value: formatCost(comparison.previous_today_cost_usd),
              })
        }
        delta={renderDelta(comparison.today_delta_pct)}
      />
      <PageMetricStripItem
        label={t("costs.kpis.costPerResolved")}
        value={formatCost(overview.avg_cost_per_resolved_conversation)}
        hint={t("costs.page.kpiContexts.resolvedConversations", {
          defaultValue: "{{count}} resolved conversations",
          count: overview.resolved_conversations,
        })}
        delta={renderDelta(comparison.avg_cost_per_resolved_delta_pct)}
      />
      <PageMetricStripItem
        label={t("costs.kpis.peakBucket")}
        value={peakBucket ? formatCost(peakBucket.cost_usd) : "—"}
        hint={peakContext}
      />
    </PageMetricStrip>
  );
}
