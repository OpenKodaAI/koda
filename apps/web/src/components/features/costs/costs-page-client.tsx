"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CostBreakdownCard, type CostBreakdownItem } from "@/components/costs/cost-breakdown-card";
import { CostConversationTable } from "@/components/costs/cost-conversation-table";
import { CostDonutChart, type CostDonutMode } from "@/components/costs/cost-donut-chart";
import { CostKpiRail } from "@/components/costs/cost-kpi-rail";
import { CostTimeChart, type CostTimelineMode } from "@/components/costs/cost-time-chart";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
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
import { resolveAgentSelection } from "@/lib/agent-selection";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { CostGroupBy, CostInsightsResponse } from "@/lib/types";
import { formatCost } from "@/lib/utils";

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

function buildAgentItems(
  insights: CostInsightsResponse | null,
  tl: (value: string, options?: Record<string, unknown>) => string
): CostBreakdownItem[] {
  return (
    insights?.by_bot?.map((entry) => ({
      id: entry.bot_id,
      label: getAgentLabel(entry.bot_id),
      value: entry.cost_usd,
      share: entry.share_pct,
      color: getAgentColor(entry.bot_id),
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
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
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
        />

        <div className="w-full md:w-auto md:flex-none md:ml-auto">
          <Select value={effectiveModelFilter} onValueChange={setModelFilter}>
            <SelectTrigger
              aria-label={t("costs.filters.model")}
              className="min-w-[180px] md:w-auto"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("common.allModels")}</SelectItem>
              {(insights.available_models ?? []).map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-full md:w-auto md:flex-none">
          <Select value={effectiveTaskTypeFilter} onValueChange={setTaskTypeFilter}>
            <SelectTrigger
              aria-label={t("costs.filters.taskType")}
              className="min-w-[180px] md:w-auto"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("common.allTypes")}</SelectItem>
              {(insights.available_task_types ?? []).map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
