"use client";


import { useCallback, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { DatabaseZap, ShieldCheck } from "lucide-react";
import { DLQTable } from "@/components/dlq/dlq-table";
import { ErrorDetail } from "@/components/dlq/error-detail";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { DLQDataLoading } from "@/components/layout/route-loading";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import { InfiniteListFooter } from "@/components/ui/infinite-list-footer";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import {
  PageEmptyState,
  PageMetricStrip,
  PageMetricStripItem,
} from "@/components/ui/page-primitives";
import { SoftTabs } from "@/components/ui/soft-tabs";
import {
  formatAgentSelectionLabel,
  resolveAgentSelection,
} from "@/lib/agent-selection";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import {
  DASHBOARD_CACHE_GC_MS,
  DASHBOARD_CACHE_STALE_MS,
  DASHBOARD_PAGE_SIZE,
  mergePaginatedItems,
  normalizePaginatedListResponse,
  type PaginatedListResponse,
} from "@/lib/pagination";
import { queryKeys } from "@/lib/query/keys";
import type { DLQEntry } from "@/lib/types";

type DLQPage = PaginatedListResponse<DLQEntry> & {
  unavailable?: boolean;
};

export default function DLQPage() {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<DLQEntry | null>(null);
  const [retryFilter, setRetryFilter] = useState<string>("");
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const dlqFilters = useMemo(() => ({
    agentIds: visibleBotIds,
    retryFilter,
    limit: DASHBOARD_PAGE_SIZE,
  }), [retryFilter, visibleBotIds]);
  const entriesQuery = useInfiniteQuery<DLQPage, Error>({
    queryKey: queryKeys.dashboard.dlqPages(dlqFilters),
    initialPageParam: 0,
    staleTime: DASHBOARD_CACHE_STALE_MS,
    gcTime: DASHBOARD_CACHE_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    getNextPageParam: (lastPage) =>
      lastPage.page.has_more ? lastPage.page.next_offset : undefined,
    queryFn: async ({ signal, pageParam }) => {
      const offset = typeof pageParam === "number" ? pageParam : 0;
      const response = await fetchControlPlaneDashboardJsonAllowError<
        PaginatedListResponse<DLQEntry>
      >(
        "/dlq",
        {
          signal,
          params: {
            paged: 1,
            agent: visibleBotIds,
            limit: DASHBOARD_PAGE_SIZE,
            offset,
            retryEligible:
              retryFilter === "eligible"
                ? true
                : retryFilter === "ineligible"
                  ? false
                  : null,
          },
          fallbackError: t("dlq.page.unavailableDescription"),
        },
      );

      const page = normalizePaginatedListResponse<DLQEntry>(
        response.data,
        DASHBOARD_PAGE_SIZE,
        offset,
      );
      return {
        ...page,
        items: [...page.items].sort(
          (left, right) =>
            new Date(right.failed_at).getTime() - new Date(left.failed_at).getTime(),
        ),
        unavailable: !response.ok,
      };
    },
  });
  const stableEntriesQuery = useStableQueryData({
    data: entriesQuery.data,
    resetKey: JSON.stringify(dlqFilters),
    isPending: entriesQuery.isPending,
    isFetching: entriesQuery.isFetching,
    error: entriesQuery.error,
  });
  const entries = useMemo(
    () =>
      mergePaginatedItems(stableEntriesQuery.data?.pages, (entry) => entry.id).sort(
        (left, right) =>
          new Date(right.failed_at).getTime() - new Date(left.failed_at).getTime(),
      ),
    [stableEntriesQuery.data],
  );
  const loading = stableEntriesQuery.initialLoading;
  const unavailable = stableEntriesQuery.data?.pages.some((page) => page.unavailable) ?? false;
  const loadMoreEntries = useCallback(() => {
    if (!entriesQuery.hasNextPage || entriesQuery.isFetchingNextPage) return;
    void entriesQuery.fetchNextPage();
  }, [entriesQuery]);
  const selectionLabel = formatAgentSelectionLabel(visibleBotIds, agents);
  const retryEligibleCount = entries.filter(
    (entry) => entry.retry_eligible === 1 && !entry.retried_at
  ).length;
  const retriedCount = entries.filter((entry) => Boolean(entry.retried_at)).length;
  const affectedAgents = new Set(entries.map((entry) => entry.bot_id).filter(Boolean)).size;

  const filterButtons = [
    { value: "", label: t("dlq.page.all") },
    { value: "eligible", label: t("dlq.page.retryEligible") },
    { value: "ineligible", label: t("dlq.page.noRetry") },
  ];

  const emptyTitle =
    retryFilter === "eligible"
      ? t("dlq.page.emptyEligible")
      : retryFilter === "ineligible"
        ? t("dlq.page.emptyIneligible")
        : t("dlq.page.emptyDefault");
  const emptyDescription =
    retryFilter === "eligible"
      ? t("dlq.page.emptyEligibleDescription")
      : retryFilter === "ineligible"
        ? t("dlq.page.emptyIneligibleDescription")
        : t("dlq.page.emptyDefaultDescription");

  return (
    <>
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
          <div className="w-full md:w-auto md:shrink-0 md:ml-auto">
            <SoftTabs
              items={filterButtons.map((filter) => ({
                id: filter.value || "__all__",
                label: filter.label,
              }))}
              value={retryFilter || "__all__"}
              onChange={(id) => setRetryFilter(id === "__all__" ? "" : id)}
              ariaLabel={t("dlq.page.all")}
            />
          </div>
        </div>

        {loading && entries.length === 0 ? (
          <DLQDataLoading />
        ) : stableEntriesQuery.showBlockingError ? (
            <ErrorState
              title={t("dlq.page.unavailable")}
              description={entriesQuery.error?.message ?? t("dlq.page.unavailableDescription")}
              onRetry={() => {
              void entriesQuery.refetch();
            }}
          />
        ) : (
          <>
            <PageMetricStrip>
              <PageMetricStripItem
                label={t("dlq.page.visibleFailures")}
                value={`${entries.length}`}
                hint={loading ? t("common.loading") : t("dlq.page.orderedByRecent")}
              />
              <PageMetricStripItem
                label={t("dlq.page.retryEligible")}
                value={`${retryEligibleCount}`}
                hint={t("dlq.page.retryEligibleHint")}
              />
              <PageMetricStripItem
                label={t("dlq.page.alreadyRetried")}
                value={`${retriedCount}`}
                hint={t("dlq.page.alreadyRetriedHint")}
              />
              <PageMetricStripItem
                label={t("dlq.page.affectedAgents")}
                value={`${affectedAgents}`}
                hint={selectionLabel}
              />
            </PageMetricStrip>

            {unavailable ? (
              <div className="px-6 py-10">
                <PageEmptyState
                  icon={DatabaseZap}
                  title={t("dlq.page.unavailable")}
                  description={t("dlq.page.unavailableDescription")}
                />
              </div>
            ) : entries.length === 0 ? (
              <div className="px-6 py-10">
                <PageEmptyState
                  icon={ShieldCheck}
                  title={emptyTitle}
                  description={emptyDescription}
                />
              </div>
            ) : (
              <div>
                <DLQTable
                  entries={entries}
                  onEntryClick={setSelectedEntry}
                  selectedEntryId={selectedEntry?.id ?? null}
                />
                <InfiniteListFooter
                  hasMore={Boolean(entriesQuery.hasNextPage)}
                  loading={entriesQuery.isFetchingNextPage}
                  onLoadMore={loadMoreEntries}
                  label={t("common.loadMore", undefined)}
                />
              </div>
            )}
          </>
        )}
      </div>

      <ErrorDetail entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
    </>
  );
}
