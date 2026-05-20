"use client";


import dynamic from "next/dynamic";
import { useState, useCallback, useEffect, useMemo } from "react";
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { ExecutionTable } from "@/components/executions/execution-table";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { ExecutionsRouteLoading } from "@/components/layout/route-loading";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import {
  PageMetricStrip,
  PageMetricStripItem,
  PageQueryState,
  PageSearchField,
} from "@/components/ui/page-primitives";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { InfiniteListFooter } from "@/components/ui/infinite-list-footer";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useMinDurationFlag } from "@/hooks/use-min-duration-flag";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useUrlSyncedSearch } from "@/hooks/use-url-synced-search";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { resolveAgentSelection } from "@/lib/agent-selection";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
} from "@/lib/control-plane-dashboard";
import {
  DASHBOARD_CACHE_GC_MS,
  DASHBOARD_CACHE_STALE_MS,
  DASHBOARD_PAGE_SIZE,
  mergePaginatedItems,
  normalizePaginatedListResponse,
  type PaginatedListResponse,
} from "@/lib/pagination";
import { queryKeys } from "@/lib/query/keys";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/types";
import { formatCost, formatDuration } from "@/lib/utils";

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

type ExecutionPage = PaginatedListResponse<ExecutionSummary> & {
  unavailable?: boolean;
};

export default function ExecutionsPage() {
  const { t, language } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [isExecutionModalOpen, setIsExecutionModalOpen] = useState(false);
  const searchState = useUrlSyncedSearch({ debounceMs: 260 });
  const search = searchState.value;
  const setSearch = searchState.setValue;
  const debouncedSearch = searchState.debouncedValue;
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const executionFilters = useMemo(() => ({
    agentIds: visibleBotIds,
    status: statusFilter,
    search: debouncedSearch,
    limit: DASHBOARD_PAGE_SIZE,
  }), [debouncedSearch, statusFilter, visibleBotIds]);
  const executionsQuery = useInfiniteQuery<ExecutionPage, Error>({
    queryKey: queryKeys.dashboard.executionPages(executionFilters),
    initialPageParam: 0,
    staleTime: DASHBOARD_CACHE_STALE_MS,
    gcTime: DASHBOARD_CACHE_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
    getNextPageParam: (lastPage) =>
      lastPage.page.has_more ? lastPage.page.next_offset : undefined,
    queryFn: async ({ signal, pageParam }) => {
      const offset = typeof pageParam === "number" ? pageParam : 0;
      const response = await fetchControlPlaneDashboardJsonAllowError<
        PaginatedListResponse<ExecutionSummary>
      >(
        "/executions",
        {
          signal,
          params: {
            paged: 1,
            agent: visibleBotIds,
            status: statusFilter || null,
            search: debouncedSearch || null,
            limit: DASHBOARD_PAGE_SIZE,
            offset,
          },
          fallbackError: t("executions.page.loadError"),
        },
      );

      const page = normalizePaginatedListResponse<ExecutionSummary>(
        response.data,
        DASHBOARD_PAGE_SIZE,
        offset,
      );
      return {
        ...page,
        items: [...page.items].sort(
          (left, right) =>
            new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
        ),
        unavailable: !response.ok,
      };
    },
  });

  const stableExecutionsQuery = useStableQueryData({
    data: executionsQuery.data,
    resetKey: JSON.stringify(executionFilters),
    isPending: executionsQuery.isPending,
    isFetching: executionsQuery.isFetching,
    error: executionsQuery.error,
  });
  const executions = useMemo(
    () =>
      mergePaginatedItems(
        stableExecutionsQuery.data?.pages,
        (execution) => `${execution.bot_id}:${execution.task_id}`,
      ).sort(
        (left, right) =>
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      ),
    [stableExecutionsQuery.data]
  );
  const unavailable = stableExecutionsQuery.data?.pages.some((page) => page.unavailable) ?? false;
  const loading = stableExecutionsQuery.initialLoading;
  const loadMoreExecutions = useCallback(() => {
    if (!executionsQuery.hasNextPage || executionsQuery.isFetchingNextPage) return;
    void executionsQuery.fetchNextPage();
  }, [executionsQuery]);

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
  const handleAgentSelectionChange = useCallback((agentIds: string[]) => {
    clearSelection();
    setSelectedBotIds(agentIds);
  }, [clearSelection]);
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
  }, [setSearch]);
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
  const refreshExecutions = useCallback(() => {
    void executionsQuery.refetch();
  }, [executionsQuery]);
  const searchLoading =
    searchState.isSearching ||
    (executionsQuery.isFetching &&
      !executionsQuery.isFetchingNextPage &&
      search.trim() === debouncedSearch);

  useEffect(() => {
    if (!selectedExecution || executionsQuery.isFetching) return;
    const stillVisible = executions.some(
      (execution) =>
        execution.bot_id === selectedExecution.bot_id &&
        execution.task_id === selectedExecution.task_id,
    );
    if (stillVisible) return;
    const frame = window.requestAnimationFrame(() => clearSelection());
    return () => window.cancelAnimationFrame(frame);
  }, [clearSelection, executions, executionsQuery.isFetching, selectedExecution]);

  const showInitialSkeleton = useMinDurationFlag(loading && executions.length === 0, 350);
  if (showInitialSkeleton) {
    return <ExecutionsRouteLoading />;
  }

  const tourVariant =
    stableExecutionsQuery.showBlockingError || (unavailable && executions.length === 0)
      ? "unavailable"
      : executions.length === 0
        ? "empty"
        : "default";

  return (
    <>
      <div className="min-w-0 space-y-4" {...tourRoute("executions", tourVariant)}>
        <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
          <div
            className="w-full md:w-[220px] md:flex-none"
            {...tourAnchor("executions.agent-switcher")}
          >
            <AgentSwitcher
              multiple
              singleRow
              className="agent-switcher--compact"
              selectedBotIds={selectedBotIds}
              onSelectionChange={handleAgentSelectionChange}
            />
          </div>
          <div className="w-full md:min-w-[200px] md:flex-1" {...tourAnchor("executions.search")}>
            <PageSearchField
              className="w-full"
              value={search}
              onChange={handleSearchChange}
              placeholder={t("executions.searchPlaceholder")}
              loading={searchLoading}
              loadingLabel={t("executions.searching", undefined)}
              clearLabel={t("common.clear", undefined)}
            />
          </div>
          <div className="w-full md:w-auto md:shrink-0" {...tourAnchor("executions.status-filters")}>
            <SoftTabs
              items={statuses.map((status) => ({
                id: status.value || "__all__",
                label: status.label,
              }))}
              value={statusFilter || "__all__"}
              onChange={(id) => handleStatusFilterChange(id === "__all__" ? "" : id)}
              ariaLabel={t("executions.page.statusAll")}
            />
          </div>
        </div>

        <div {...tourAnchor("executions.metrics")}>
          <PageMetricStrip>
            <PageMetricStripItem
              label={t("executions.page.metrics.cost")}
              value={totalCostDisplay}
              hint={t("executions.page.metrics.costHint")}
            />
            <PageMetricStripItem
              label={t("executions.page.metrics.avgDuration")}
              value={avgDurationDisplay}
              hint={t("executions.page.metrics.avgDurationHint")}
            />
            <PageMetricStripItem
              label={t("executions.page.metrics.tools")}
              value={totalToolsDisplay}
              hint={t("executions.page.metrics.toolsHint")}
            />
            <PageMetricStripItem
              label={t("executions.page.metrics.warnings")}
              value={totalWarningsDisplay}
              hint={t("executions.page.metrics.warningsHint")}
            />
          </PageMetricStrip>
        </div>

        {stableExecutionsQuery.showBlockingError ? (
          <div {...tourAnchor("executions.unavailable")}>
            <ErrorState
              title={t("executions.unavailable")}
              description={executionsQuery.error?.message ?? t("executions.loadError")}
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
              onExecutionClick={setSelectedExecution}
              selectedExecutionId={selectedExecution?.task_id ?? null}
            />
            <InfiniteListFooter
              hasMore={Boolean(executionsQuery.hasNextPage)}
              loading={executionsQuery.isFetchingNextPage}
              onLoadMore={loadMoreExecutions}
              label={t("common.loadMore", undefined)}
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
