"use client";


import dynamic from "next/dynamic";
import { useState, useCallback, useMemo } from "react";
import { Workflow } from "lucide-react";
import { ExecutionTable } from "@/components/executions/execution-table";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import {
  PageFilterChips,
  PageMetricStrip,
  PageMetricStripItem,
  PageQueryState,
  PageSearchField,
} from "@/components/ui/page-primitives";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { resolveBotSelection } from "@/lib/bot-selection";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/types";
import { cn, formatCost, formatDuration } from "@/lib/utils";

const ExecutionDetailDrawer = dynamic(
  () =>
    import("@/components/executions/execution-detail-drawer").then((module) => ({
      default: module.ExecutionDetailDrawer,
    })),
  { loading: () => null },
);

const ExecutionDetailModal = dynamic(
  () =>
    import("@/components/executions/execution-detail-modal").then((module) => ({
      default: module.ExecutionDetailModal,
    })),
  { loading: () => null },
);

export default function ExecutionsPage() {
  const { t, language } = useAppI18n();
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [isExecutionModalOpen, setIsExecutionModalOpen] = useState(false);
  const debouncedSearch = useDebouncedValue(search.trim(), 260);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const executionsQuery = useControlPlaneQuery<{
    items: ExecutionSummary[];
    unavailable: boolean;
  }>({
    tier: "live",
    queryKey: queryKeys.dashboard.executions({
      botIds: visibleBotIds,
      status: statusFilter,
      search: debouncedSearch,
      limit: 100,
    }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const hasActive = items.some((e) =>
        ["running", "queued", "retrying"].includes(e.status),
      );
      return hasActive ? 10_000 : 45_000;
    },
    queryFn: async ({ signal }) => {
      const response = await fetchControlPlaneDashboardJsonAllowError<ExecutionSummary[]>(
        "/executions",
        {
          signal,
          params: {
            bot: visibleBotIds,
            status: statusFilter || null,
            search: debouncedSearch || null,
            limit: 100,
          },
          fallbackError: t("executions.page.loadError"),
        },
      );

      const merged = Array.isArray(response.data)
        ? [...response.data].sort(
            (left, right) =>
              new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
          )
        : [];
      return {
        items: merged,
        unavailable: !response.ok,
      };
    },
  });

  const executions = useMemo(
    () => executionsQuery.data?.items ?? [],
    [executionsQuery.data]
  );
  const unavailable = executionsQuery.data?.unavailable ?? false;
  const loading = executionsQuery.isLoading;

  const detailQuery = useControlPlaneQuery<ExecutionDetail>({
    tier: "live",
    enabled: Boolean(selectedExecution),
    queryKey: selectedExecution
      ? queryKeys.dashboard.executionDetail(
          selectedExecution.bot_id,
          selectedExecution.task_id,
          language,
        )
      : ["dashboard", "executions", "detail", "idle"],
    refetchInterval: (query) => {
      if (!selectedExecution) return false;
      const status = query.state.data?.status;
      const isActive = ["running", "queued", "retrying"].includes(status ?? "");
      return isActive ? 5_000 : 30_000;
    },
    queryFn: async ({ signal }) => {
      if (!selectedExecution) {
        throw new Error(t("executions.page.noSelection"));
      }

      return fetchControlPlaneDashboardJson<ExecutionDetail>(
        `/agents/${selectedExecution.bot_id}/executions/${selectedExecution.task_id}`,
        {
          signal,
          params: { lang: language },
          fallbackError: t("executions.page.detailLoadError"),
        },
      );
    },
  });

  const selectedDetail = detailQuery.data ?? null;
  const detailLoading = detailQuery.isLoading;
  const detailError = detailQuery.error?.message ?? null;

  const statuses = [
    { value: "", label: t("executions.page.statusAll") },
    { value: "completed", label: t("executions.page.statusCompleted") },
    { value: "running", label: t("executions.page.statusRunning") },
    { value: "queued", label: t("executions.page.statusQueued") },
    { value: "failed", label: t("executions.page.statusFailed") },
    { value: "retrying", label: t("executions.page.statusRetrying") },
  ];

  const clearSelection = useCallback(() => {
    setSelectedExecution(null);
    setIsExecutionModalOpen(false);
  }, []);
  const handleBotSelectionChange = useCallback((botIds: string[]) => {
    clearSelection();
    setSelectedBotIds(botIds);
  }, [clearSelection]);
  const handleSearchChange = useCallback((value: string) => {
    clearSelection();
    setSearch(value);
  }, [clearSelection]);
  const handleStatusFilterChange = useCallback((value: string) => {
    clearSelection();
    setStatusFilter(value);
  }, [clearSelection]);

  const aggregates = useMemo(() => {
    const totalCost = executions.reduce((sum, e) => sum + (e.cost_usd ?? 0), 0);
    const totalDuration = executions.reduce((sum, e) => sum + (e.duration_ms ?? 0), 0);
    const avgDuration = executions.length > 0 ? totalDuration / executions.length : 0;
    const totalTools = executions.reduce((sum, e) => sum + (e.tool_count ?? 0), 0);
    const totalWarnings = executions.reduce((sum, e) => sum + (e.warning_count ?? 0), 0);
    return { totalCost, avgDuration, totalTools, totalWarnings };
  }, [executions]);

  const totalCostDisplay = formatCost(aggregates.totalCost);
  const avgDurationDisplay = formatDuration(aggregates.avgDuration);
  const totalToolsDisplay = String(aggregates.totalTools);
  const totalWarningsDisplay = String(aggregates.totalWarnings);
  const showInitialSkeleton = loading && executions.length === 0;
  const refreshExecutions = useCallback(() => {
    void executionsQuery.refetch();
  }, [executionsQuery]);
  const tourVariant =
    executionsQuery.error || unavailable
      ? "unavailable"
      : showInitialSkeleton
        ? "loading"
        : executions.length === 0
          ? "empty"
          : "default";

  return (
    <>
      <div className="min-w-0 space-y-4" {...tourRoute("executions", tourVariant)}>
        <div className="flex flex-col gap-4 md:flex-row md:flex-wrap xl:flex-nowrap xl:items-center">
          <div
            className="w-full md:max-w-[350px] md:min-w-[200px] xl:w-[320px] xl:flex-none"
            {...tourAnchor("executions.bot-switcher")}
          >
            <BotSwitcher
              multiple
              selectedBotIds={selectedBotIds}
              onSelectionChange={handleBotSelectionChange}
            />
          </div>
          <div className="flex min-w-0 flex-col gap-4 md:flex-1 md:flex-row md:flex-wrap md:items-center md:justify-end">
            <div className="w-full md:min-w-[240px] md:flex-1 md:max-w-[24rem]" {...tourAnchor("executions.search")}>
              <PageSearchField
                className="w-full md:max-w-[24rem] xl:w-[320px]"
                value={search}
                onChange={handleSearchChange}
                placeholder={t("executions.searchPlaceholder")}
              />
            </div>
            <div className="w-full md:w-auto md:max-w-full" {...tourAnchor("executions.status-filters")}>
              <PageFilterChips className="w-full justify-start md:w-auto md:max-w-full md:justify-end">
                {statuses.map((status) => (
                  <button
                    key={status.value}
                    type="button"
                    onClick={() => handleStatusFilterChange(status.value)}
                    className={cn("button-pill", statusFilter === status.value && "is-active")}
                  >
                    {status.label}
                  </button>
                ))}
              </PageFilterChips>
            </div>
          </div>
        </div>

        <div {...tourAnchor("executions.metrics")}>
          <PageMetricStrip>
          {showInitialSkeleton ? (
            Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="metric-strip__item">
                <div className="skeleton h-3 w-16 rounded-xl" />
                <div className="mt-2 skeleton h-6 w-20 rounded-xl" />
              </div>
            ))
          ) : (
            <>
              <PageMetricStripItem
                label={t("executions.page.metrics.cost")}
                value={totalCostDisplay}
              />
              <PageMetricStripItem
                label={t("executions.page.metrics.avgDuration")}
                value={avgDurationDisplay}
              />
              <PageMetricStripItem
                label={t("executions.page.metrics.tools")}
                value={totalToolsDisplay}
              />
              <PageMetricStripItem
                label={t("executions.page.metrics.warnings")}
                value={totalWarningsDisplay}
              />
            </>
          )}
          </PageMetricStrip>
        </div>

        {showInitialSkeleton ? (
          <div {...tourAnchor("executions.table")}>
            <ExecutionTable executions={[]} showBot loading />
          </div>
        ) : executionsQuery.error ? (
          <div {...tourAnchor("executions.unavailable")}>
            <ErrorState
              title={t("executions.unavailable")}
              description={executionsQuery.error.message ?? t("executions.loadError")}
              onRetry={refreshExecutions}
            />
          </div>
        ) : unavailable ? (
          <div {...tourAnchor("executions.unavailable")}>
            <PageQueryState
              visual={<Workflow className="empty-state-icon h-10 w-10" />}
              title={t("executions.unavailable")}
            />
          </div>
        ) : (
          <div {...tourAnchor("executions.table")}>
            <ExecutionTable
              executions={executions}
              showBot={visibleBotIds.length !== 1}
              onExecutionClick={setSelectedExecution}
              selectedExecutionId={selectedExecution?.task_id ?? null}
            />
          </div>
        )}
      </div>

      {selectedExecution ? (
        <div {...tourAnchor("executions.detail-drawer")}>
          <ExecutionDetailDrawer
            execution={selectedExecution}
            detail={selectedDetail}
            loading={detailLoading}
            error={detailError}
            onClose={clearSelection}
            onExpand={() => setIsExecutionModalOpen(true)}
            modalOpen={isExecutionModalOpen}
          />
        </div>
      ) : null}

      {selectedExecution ? (
        <ExecutionDetailModal
          execution={selectedExecution}
          detail={selectedDetail}
          loading={detailLoading}
          error={detailError}
          isOpen={isExecutionModalOpen}
          onClose={() => setIsExecutionModalOpen(false)}
        />
      ) : null}
    </>
  );
}
