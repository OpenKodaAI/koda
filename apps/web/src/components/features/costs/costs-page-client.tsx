"use client";

import { useMemo, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CostBreakdownCard, type CostBreakdownItem } from "@/components/costs/cost-breakdown-card";
import { CostDonutChart, type CostDonutMode } from "@/components/costs/cost-donut-chart";
import { CostKpiRail } from "@/components/costs/cost-kpi-rail";
import { CostTimeChart, type CostTimelineMode } from "@/components/costs/cost-time-chart";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { CostRouteLoading } from "@/components/layout/route-loading";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useMinDurationFlag } from "@/hooks/use-min-duration-flag";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { resolveAgentSelection } from "@/lib/agent-selection";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { CostGroupBy, CostInsightsResponse } from "@/lib/types";
import { formatCost } from "@/lib/utils";

const PERIOD_VALUES = ["7d", "30d", "90d"] as const;

const MODEL_COLORS = [
  "var(--tone-info-dot)",
  "var(--tone-success-dot)",
  "var(--tone-warning-dot)",
  "var(--tone-neutral-dot)",
  "var(--tone-retry-dot)",
  "var(--text-quaternary)",
];
const TASK_TYPE_COLORS = [
  "var(--tone-neutral-dot)",
  "var(--tone-info-dot)",
  "var(--tone-success-dot)",
  "var(--tone-warning-dot)",
  "var(--tone-retry-dot)",
  "var(--text-quaternary)",
];

function buildModelItems(
  insights: CostInsightsResponse | null,
  tl: (value: string, options?: Record<string, unknown>) => string
): CostBreakdownItem[] {
  return (
    insights?.by_model?.map((entry, index) => ({
      id: entry.model,
      label: entry.model,
      value: entry.cost_usd,
      share: entry.share_pct,
      color: MODEL_COLORS[index % MODEL_COLORS.length],
      meta: tl("{{queries}} consultas · {{executions}} execuções", {
        queries: entry.query_count,
        executions: entry.execution_count,
      }),
    })) ?? []
  );
}

function buildAgentItems(
  insights: CostInsightsResponse | null,
  tl: (value: string, options?: Record<string, unknown>) => string
): CostBreakdownItem[] {
  return (
    insights?.by_agent?.map((entry) => ({
      id: entry.agent_id,
      label: getAgentLabel(entry.agent_id),
      value: entry.cost_usd,
      share: entry.share_pct,
      color: getAgentColor(entry.agent_id),
      meta: tl("{{resolved}} resolvidas · {{cost}}/conv.", {
        resolved: entry.resolved_conversations,
        cost: formatCost(entry.avg_cost_per_resolved_conversation),
      }),
    })) ?? []
  );
}

function buildTaskItems(
  insights: CostInsightsResponse | null,
  tl: (value: string, options?: Record<string, unknown>) => string
): CostBreakdownItem[] {
  return (
    insights?.by_task_type?.map((entry, index) => ({
      id: entry.task_type,
      label: entry.label,
      value: entry.cost_usd,
      share: entry.share_pct,
      color: TASK_TYPE_COLORS[index % TASK_TYPE_COLORS.length],
      meta: tl("{{count}} eventos · {{cost}} méd.", {
        count: entry.count,
        cost: formatCost(entry.avg_cost_usd),
      }),
    })) ?? []
  );
}

export default function CostsPage() {
  const { t, tl, language } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [period, setPeriod] = useState<(typeof PERIOD_VALUES)[number]>("30d");
  const [groupBy] = useState<CostGroupBy>("auto");
  const [timelineMode, setTimelineMode] = useState<CostTimelineMode>("agent");
  const [allocationMode, setAllocationMode] = useState<CostDonutMode>("task");
  const [modelFilter, setModelFilter] = useState("all");
  const [taskTypeFilter, setTaskTypeFilter] = useState("all");
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const periodOptions = useMemo(
    () =>
      PERIOD_VALUES.map((value) => ({
        value,
        label: t(`costs.filters.periods.${value}`),
      })),
    [t]
  );
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );

  const insightsQuery = useControlPlaneQuery<CostInsightsResponse>({
    tier: "detail",
    queryKey: queryKeys.dashboard.costs({
      agentIds: selectedBotIds.length > 0 ? visibleBotIds : [],
      period,
      groupBy,
      model: modelFilter,
      taskType: taskTypeFilter,
      language,
    }),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<CostInsightsResponse>(
        "/costs",
        {
          signal,
          params: {
            period,
            groupBy,
            agent: selectedBotIds.length > 0 ? visibleBotIds : null,
            model: modelFilter !== "all" ? modelFilter : null,
            taskType: taskTypeFilter !== "all" ? taskTypeFilter : null,
            lang: language,
          },
          fallbackError: t("costs.page.loadError", { defaultValue: "Could not load costs." }),
        },
      ),
  });

  const stableInsightsQuery = useStableQueryData({
    data: insightsQuery.data,
    resetKey: "dashboard:costs",
    isPending: insightsQuery.isPending,
    isFetching: insightsQuery.isFetching,
    error: insightsQuery.error,
  });
  const insights = stableInsightsQuery.data ?? null;
  const loading = stableInsightsQuery.initialLoading;
  const error =
    insightsQuery.error?.message ??
    null;
  const effectiveModelFilter =
    insights && modelFilter !== "all" && !insights.available_models?.includes(modelFilter)
      ? "all"
      : modelFilter;
  const effectiveTaskTypeFilter =
    insights &&
    taskTypeFilter !== "all" &&
    !insights.available_task_types?.some((item) => item.value === taskTypeFilter)
      ? "all"
      : taskTypeFilter;

  const overview = insights?.overview;
  const byAgentItems = useMemo(() => buildAgentItems(insights, tl), [insights, tl]);
  const byModelItems = useMemo(() => buildModelItems(insights, tl), [insights, tl]);
  const byTaskItems = useMemo(() => buildTaskItems(insights, tl), [insights, tl]);

  const allocationItems = useMemo(() => {
    if (allocationMode === "agent") return byAgentItems;
    if (allocationMode === "model") return byModelItems;
    return byTaskItems;
  }, [allocationMode, byAgentItems, byModelItems, byTaskItems]);

  const allocationRange = useMemo(() => {
    const series = insights?.time_series;
    if (!series?.length) return { start: null, end: null };
    return {
      start: series[0]?.label ?? null,
      end: series[series.length - 1]?.label ?? null,
    };
  }, [insights]);

  const showInitialSkeleton = useMinDurationFlag(loading && !insights, 350);

  if (stableInsightsQuery.showBlockingError && error) {
    return (
      <ErrorState
        title={t("costs.page.unavailable", { defaultValue: "Costs unavailable" })}
        description={error}
        onRetry={() => {
          void insightsQuery.refetch();
        }}
      />
    );
  }

  if (showInitialSkeleton) {
    return <CostRouteLoading />;
  }

  if (!insights || !overview) {
    return null;
  }

  return (
    <div className="min-w-0 space-y-3">
      <section className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] px-3 py-2.5">
        <div className="flex min-w-0 flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-center">
            <div className="w-full md:w-[220px] md:flex-none">
              <AgentSwitcher
                multiple
                singleRow
                className="agent-switcher--compact"
                selectedBotIds={selectedBotIds}
                onSelectionChange={setSelectedBotIds}
              />
            </div>

            <SoftTabs
              items={periodOptions.map((option) => ({ id: option.value, label: option.label }))}
              value={period}
              onChange={(id) => setPeriod(id as (typeof PERIOD_VALUES)[number])}
              ariaLabel={t("costs.filters.period", { defaultValue: "Period" })}
              className="w-fit"
            />
          </div>

          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center xl:justify-end">
            <Select value={effectiveModelFilter} onValueChange={setModelFilter}>
              <SelectTrigger
                aria-label={t("costs.filters.model")}
                sizeVariant="sm"
                className="min-w-[154px] rounded-[var(--radius-panel-sm)]"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("common.allModels")}</SelectItem>
                {(insights?.available_models ?? []).map((model) => (
                  <SelectItem key={model} value={model}>
                    {model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={effectiveTaskTypeFilter} onValueChange={setTaskTypeFilter}>
              <SelectTrigger
                aria-label={t("costs.filters.taskType")}
                sizeVariant="sm"
                className="min-w-[154px] rounded-[var(--radius-panel-sm)]"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("common.allTypes")}</SelectItem>
                {(insights?.available_task_types ?? []).map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>

      <CostKpiRail
        overview={overview}
        comparison={insights.comparison ?? null}
        peakBucket={insights.peak_bucket ?? null}
      />

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.48fr)_minmax(300px,0.72fr)] xl:items-stretch">
        <CostTimeChart
          points={insights.time_series ?? []}
          mode={timelineMode}
          onModeChange={setTimelineMode}
        />

        <CostDonutChart
          items={allocationItems}
          mode={allocationMode}
          onModeChange={setAllocationMode}
          totalLabel={t("costs.page.shareInPeriod", { defaultValue: "Share in period" })}
          rangeStartLabel={allocationRange.start ?? undefined}
          rangeEndLabel={allocationRange.end ?? undefined}
          compact
        />
      </section>

      <section className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] px-3 py-3">
        <div className="flex min-w-0 items-center justify-between gap-3 border-b border-[var(--divider-hair)] pb-2.5">
          <div className="min-w-0">
            <p className="eyebrow truncate">
              {t("costs.page.distributionEyebrow", { defaultValue: "Distribution" })}
            </p>
            <h3 className="mt-1 truncate text-[var(--font-size-sm)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {t("costs.page.distributionTitle", {
                defaultValue: "Agents, models and task types",
              })}
            </h3>
          </div>
          <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
            {formatCost(overview.total_cost_usd)}
          </span>
        </div>

        <div className="mt-2.5 grid gap-4 xl:grid-cols-3">
          <CostBreakdownCard
            title={t("costs.page.breakdowns.byAgentTitle", { defaultValue: "Distribution by agent" })}
            items={byAgentItems}
          />
          <CostBreakdownCard
            title={t("costs.page.breakdowns.byModelTitle", { defaultValue: "Distribution by model" })}
            items={byModelItems}
          />
          <CostBreakdownCard
            title={t("costs.page.breakdowns.byTaskTitle", { defaultValue: "Distribution by task type" })}
            items={byTaskItems}
          />
        </div>
      </section>

      {error ? (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="truncate rounded-[var(--radius-panel-sm)] border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-3 py-2 text-sm text-[var(--tone-danger-text)]"
        >
          {error}
        </motion.div>
      ) : null}
    </div>
  );
}
