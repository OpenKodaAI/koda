"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CostBreakdownCard, type CostBreakdownItem } from "@/components/costs/cost-breakdown-card";
import { CostConversationTable } from "@/components/costs/cost-conversation-table";
import { CostDonutChart, type CostDonutMode } from "@/components/costs/cost-donut-chart";
import { CostKpiRail } from "@/components/costs/cost-kpi-rail";
import { CostTimeChart, type CostTimelineMode } from "@/components/costs/cost-time-chart";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveBotSelection } from "@/lib/bot-selection";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { CostGroupBy, CostInsightsResponse } from "@/lib/types";
import { cn, formatCost } from "@/lib/utils";

const PERIOD_VALUES = ["7d", "30d", "90d"] as const;

const MODEL_COLORS = ["#ff4d32", "#ff7f2e", "#ffbb40", "#ffe36a", "#8fe16e", "#79cfff"];
const TASK_TYPE_COLORS = ["#ff6138", "#ff9652", "#ffbd52", "#e4e05f", "#9ce56f", "#76caff"];

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
      meta: tl(
        "{{queries}} consultas · {{executions}} execuções · {{resolved}} resolvidas",
        {
          queries: entry.query_count,
          executions: entry.execution_count,
          resolved: entry.resolved_conversations,
        },
      ),
    })) ?? []
  );
}

function buildBotItems(
  insights: CostInsightsResponse | null,
  tl: (value: string, options?: Record<string, unknown>) => string
): CostBreakdownItem[] {
  return (
    insights?.by_bot?.map((entry) => ({
      id: entry.bot_id,
      label: getBotLabel(entry.bot_id),
      value: entry.cost_usd,
      share: entry.share_pct,
      color: getBotColor(entry.bot_id),
      meta: tl("{{resolved}} resolvidas · {{cost}} por conversa", {
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
      meta: tl("{{count}} ocorrências · {{cost}} em média", {
        count: entry.count,
        cost: formatCost(entry.avg_cost_usd),
      }),
    })) ?? []
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4">
      {/* Controls bar */}
      <div className="flex flex-wrap items-start gap-4">
        <div className="max-w-[350px] min-w-[200px]">
          <div className="skeleton h-11 w-full rounded-xl" />
        </div>
        <div className="flex flex-wrap items-start gap-3">
          <div className="skeleton h-9 w-32 rounded-lg" />
          <div className="skeleton h-9 w-32 rounded-lg" />
          <div className="skeleton h-9 w-32 rounded-lg" />
        </div>
      </div>

      {/* KPI rail */}
      <div className="glass-card-sm min-h-[80px] p-4" />

      {/* Charts: time + donut */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.92fr)]">
        <div className="app-section min-h-[420px] p-5 sm:p-6" />
        <div className="app-section min-h-[420px] p-5 sm:p-6" />
      </div>

      {/* Breakdown cards */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="app-section min-h-[280px] p-5 sm:p-6" />
        <div className="app-section min-h-[280px] p-5 sm:p-6" />
        <div className="app-section min-h-[280px] p-5 sm:p-6" />
      </div>

      {/* Table */}
      <div className="app-section min-h-[320px] p-5 sm:p-6" />
    </div>
  );
}

export default function CostsPage() {
  const { t, tl, language } = useAppI18n();
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [period, setPeriod] = useState<(typeof PERIOD_VALUES)[number]>("30d");
  const [groupBy] = useState<CostGroupBy>("auto");
  const [timelineMode, setTimelineMode] = useState<CostTimelineMode>("bot");
  const [allocationMode, setAllocationMode] = useState<CostDonutMode>("task");
  const [modelFilter, setModelFilter] = useState("all");
  const [taskTypeFilter, setTaskTypeFilter] = useState("all");
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const periodOptions = useMemo(
    () =>
      PERIOD_VALUES.map((value) => ({
        value,
        label: t(`costs.filters.periods.${value}`),
      })),
    [t]
  );
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );

  const insightsQuery = useControlPlaneQuery<CostInsightsResponse>({
    tier: "detail",
    queryKey: queryKeys.dashboard.costs({
      botIds: selectedBotIds.length > 0 ? visibleBotIds : [],
      period,
      groupBy,
      model: modelFilter,
      taskType: taskTypeFilter,
      language,
    }),
    refetchInterval: 60_000,
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<CostInsightsResponse>(
        "/costs",
        {
          signal,
          params: {
            period,
            groupBy,
            bot: selectedBotIds.length > 0 ? visibleBotIds : null,
            model: modelFilter !== "all" ? modelFilter : null,
            taskType: taskTypeFilter !== "all" ? taskTypeFilter : null,
            lang: language,
          },
          fallbackError: t("costs.page.loadError", { defaultValue: "Could not load costs." }),
        },
      ),
  });

  const insights = insightsQuery.data ?? null;
  const loading = insightsQuery.isLoading;
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
  const byBotItems = useMemo(() => buildBotItems(insights, tl), [insights, tl]);
  const byModelItems = useMemo(() => buildModelItems(insights, tl), [insights, tl]);
  const byTaskItems = useMemo(() => buildTaskItems(insights, tl), [insights, tl]);

  const allocationItems = useMemo(() => {
    if (allocationMode === "bot") return byBotItems;
    if (allocationMode === "model") return byModelItems;
    return byTaskItems;
  }, [allocationMode, byBotItems, byModelItems, byTaskItems]);

  const allocationRange = useMemo(() => {
    const series = insights?.time_series;
    if (!series?.length) return { start: null, end: null };
    return {
      start: series[0]?.label ?? null,
      end: series[series.length - 1]?.label ?? null,
    };
  }, [insights]);

  if (loading && !insights) return <PageSkeleton />;

  if (error && !insights) {
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

  if (!insights || !overview) return null;

  return (
    <div className="space-y-4">
      {/* Header: Bot selector + filters */}
      <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(260px,350px)_minmax(280px,1fr)_minmax(220px,280px)_minmax(220px,280px)]">
        <div className="min-w-0">
          <BotSwitcher
            multiple
            selectedBotIds={selectedBotIds}
            onSelectionChange={setSelectedBotIds}
          />
        </div>

        <div className="min-w-0 self-stretch">
          <div className="segmented-control segmented-control--single-row costs-page__period-toggle h-full min-h-[44px]">
            {periodOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setPeriod(option.value)}
                className={cn("segmented-control__option", period === option.value && "is-active")}
                aria-pressed={period === option.value}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <label className="min-w-0 self-stretch">
          <span className="sr-only">{t("costs.filters.model")}</span>
          <select
            aria-label={t("costs.filters.model")}
            className="field-shell h-full min-h-[44px] px-4 text-sm"
            value={effectiveModelFilter}
            onChange={(event) => setModelFilter(event.target.value)}
          >
            <option value="all">{t("common.allModels")}</option>
            {(insights.available_models ?? []).map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>

        <label className="min-w-0 self-stretch">
          <span className="sr-only">{t("costs.filters.taskType")}</span>
          <select
            aria-label={t("costs.filters.taskType")}
            className="field-shell h-full min-h-[44px] px-4 text-sm"
            value={effectiveTaskTypeFilter}
            onChange={(event) => setTaskTypeFilter(event.target.value)}
          >
            <option value="all">{t("common.allTypes")}</option>
            {(insights.available_task_types ?? []).map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="space-y-4">
        <CostKpiRail
          overview={overview}
          comparison={insights.comparison ?? null}
          peakBucket={insights.peak_bucket ?? null}
        />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.92fr)] xl:items-start">
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
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <CostBreakdownCard
          title={t("costs.page.breakdowns.byBotTitle", { defaultValue: "Distribution by bot" })}
          subtitle={t("costs.page.breakdowns.byBotSubtitle", {
            defaultValue: "Who concentrates the cost and what the efficiency per resolved conversation is.",
          })}
          items={byBotItems}
        />
        <CostBreakdownCard
          title={t("costs.page.breakdowns.byModelTitle", { defaultValue: "Distribution by model" })}
          subtitle={t("costs.page.breakdowns.byModelSubtitle", {
            defaultValue: "Where model allocation is weighing on the current cut.",
          })}
          items={byModelItems}
        />
        <CostBreakdownCard
          title={t("costs.page.breakdowns.byTaskTitle", { defaultValue: "Distribution by task type" })}
          subtitle={t("costs.page.breakdowns.byTaskSubtitle", {
            defaultValue: "Dominant task type and average pressure per occurrence.",
          })}
          items={byTaskItems}
        />
      </section>

      <section>
        <CostConversationTable rows={insights.conversation_rows ?? []} />
      </section>

      {error ? (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="app-section border-[var(--tone-danger-border,rgba(255,120,120,0.18))] bg-[var(--tone-danger-bg,rgba(255,64,64,0.05))] px-4 py-3 text-sm text-[var(--tone-danger-text,rgba(255,214,214,0.88))]"
        >
          {error}
        </motion.div>
      ) : null}
    </div>
  );
}
