"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity } from "lucide-react";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveAgentSelection } from "@/lib/agent-selection";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { useRuntimeRooms } from "@/hooks/use-runtime-rooms";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import { translate } from "@/lib/i18n";
import {
  getRuntimeRowSummary,
  type RuntimeRoomFilter,
  type RuntimeRoomRow,
} from "@/lib/runtime-overview-model";
import type { RuntimeOverview } from "@/lib/runtime-types";
import { getRuntimeLabel, getRuntimeTone } from "@/lib/runtime-ui";
import type { SemanticTone } from "@/lib/theme-semantic";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import {
  PageMetricStrip,
  PageMetricStripItem,
  PageSearchField,
} from "@/components/ui/page-primitives";
import { InfiniteListFooter } from "@/components/ui/infinite-list-footer";
import { useToast } from "@/hooks/use-toast";
import {
  replaceUrlSearchParamsSilently,
  useUrlSyncedSearch,
} from "@/hooks/use-url-synced-search";
import { mergePaginatedItems } from "@/lib/pagination";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";

function toneToStatusDot(tone: SemanticTone): StatusDotTone {
  if (tone === "success" || tone === "info" || tone === "warning" || tone === "danger" || tone === "retry" || tone === "neutral") {
    return tone;
  }
  return "neutral";
}

function normalizeRuntimeNotice(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function isSilentRuntimeAvailabilityNotice(message: string) {
  const normalized = normalizeRuntimeNotice(message);
  if (!normalized.startsWith("runtime")) return false;
  return (
    normalized.includes("unavailable") ||
    normalized.includes("indisponivel") ||
    normalized.includes("no disponible") ||
    normalized.includes("disabled") ||
    normalized.includes("desabilitado") ||
    normalized.includes("deshabilitado") ||
    normalized.includes("degraded") ||
    normalized.includes("degradado")
  );
}

function logSilentRuntimeNotice(
  kind: "error" | "incident",
  detail: Record<string, string | null | undefined>,
) {
  console.info("runtime_overview_silent_notice", { kind, ...detail });
}

function readCurrentAgentParams() {
  if (typeof window === "undefined") return [];
  return new URL(window.location.href).searchParams.getAll("agent").filter(Boolean);
}

function RuntimeOverviewSkeleton() {
  return (
    <div
      className="runtime-shell space-y-6"
      data-testid="runtime-overview-skeleton"
      {...tourRoute("runtime", "loading")}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="skeleton h-5 w-40 rounded" />
          <div className="skeleton h-3 w-64 rounded" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="skeleton h-9 w-40 rounded-[var(--radius-pill)]" />
          <div className="skeleton h-9 w-64 rounded-[var(--radius-input)]" />
          <div className="skeleton h-9 w-56 rounded-[var(--radius-pill)]" />
        </div>
      </div>

      <PageMetricStrip>
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="metric-strip__item">
            <div className="skeleton h-3 w-20 rounded" />
            <div className="skeleton mt-2 h-6 w-16 rounded" />
          </div>
        ))}
      </PageMetricStrip>

      <div>
        <section className="min-h-[360px] space-y-2">
          <div className="skeleton h-4 w-32 rounded" />
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="skeleton h-10 w-full rounded" />
          ))}
        </section>
      </div>
    </div>
  );
}

const liveTableColumns =
  "grid-cols-[154px_72px_116px_92px_minmax(360px,1fr)_116px]";
const liveTablePinnedColumn =
  "sticky right-0 z-[1] -mr-3 flex h-full items-center justify-end border-l border-[var(--divider-hair)] bg-[var(--panel)] pl-3 pr-3";

function LiveRow({ row }: { row: RuntimeRoomRow }) {
  const { t } = useAppI18n();
  const agentColor = getAgentColor(row.agentId);
  const summary = truncateText(getRuntimeRowSummary(row), 120);
  const phaseTone = toneToStatusDot(getRuntimeTone(row.phase));
  const phaseLabel = getRuntimeLabel(row.phase);
  const isLive = phaseTone === "info" || phaseTone === "warning";
  const sourceLabel =
    row.source === "environment"
      ? t("runtime.overview.sources.environment", undefined)
      : t("runtime.overview.sources.queue", undefined);

  return (
    <Link
      href={`/runtime/${row.agentId}/tasks/${row.taskId}`}
      className={cn(
        "group grid w-full items-center gap-4 border-b border-[color:var(--divider-hair)] px-3 py-2.5 text-left last:border-b-0",
        "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "hover:bg-[var(--hover-tint)] focus-visible:bg-[var(--hover-tint)]",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)] focus-visible:ring-inset",
        liveTableColumns,
      )}
    >
      <span className="flex min-w-0 items-center gap-2">
        <StatusDot color={agentColor} />
        <span className="truncate font-mono text-[0.75rem] text-[var(--text-secondary)]">
          {getAgentLabel(row.agentId)}
        </span>
      </span>

      <span className="font-mono text-[0.75rem] tabular-nums text-[var(--text-quaternary)]">
        #{row.taskId}
      </span>

      <span className="flex min-w-0 items-center gap-2">
        <StatusDot tone={phaseTone} pulse={isLive} />
        <span className="truncate text-[0.75rem] text-[var(--text-tertiary)]">{phaseLabel}</span>
      </span>

      <span className="truncate font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {sourceLabel}
      </span>

      <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">
        {summary}
      </span>

      <span
        className={cn(
          liveTablePinnedColumn,
          "whitespace-nowrap text-right font-mono text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]",
          "group-hover:bg-[var(--hover-tint)] group-focus-visible:bg-[var(--hover-tint)]",
        )}
      >
        {row.updatedAt ? formatRelativeTime(row.updatedAt) : t("common.now")}
      </span>
    </Link>
  );
}

export function RuntimeOverviewScreen({
  initialBotIds,
}: {
  initialBotIds?: string[];
}) {
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const { agents } = useAgentCatalog();
  const lastErrorToastRef = useRef<string | null>(null);
  const lastRuntimeRoomsRefreshRef = useRef<number | null>(null);
  const incidentToastKeysRef = useRef<Set<string>>(new Set());
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>(initialBotIds ?? []);
  const [statusFilter, setStatusFilter] = useState<RuntimeRoomFilter>("all");
  const searchState = useUrlSyncedSearch({ debounceMs: 180 });
  const search = searchState.value;
  const setSearch = searchState.setValue;
  const debouncedSearch = searchState.debouncedValue;
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds],
  );
  const {
    overviews,
    loading,
    connected,
    error,
    lastUpdated,
  } = useRuntimeOverview(selectedBotIds);
  const runtimeRoomsQuery = useRuntimeRooms({
    agentIds: visibleBotIds,
    status: statusFilter,
    search: debouncedSearch,
  });
  const refreshRuntimeRoomsFirstPage = runtimeRoomsQuery.refreshFirstPage;

  useEffect(() => {
    const handlePopState = () => setSelectedBotIds(readCurrentAgentParams());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    replaceUrlSearchParamsSilently((params) => {
      params.delete("agent");
      selectedBotIds.forEach((agentId) => params.append("agent", agentId));
    });
  }, [selectedBotIds]);

  useEffect(() => {
    if (!lastUpdated) return;
    if (lastRuntimeRoomsRefreshRef.current === null) {
      lastRuntimeRoomsRefreshRef.current = lastUpdated;
      return;
    }
    if (lastRuntimeRoomsRefreshRef.current === lastUpdated) return;
    lastRuntimeRoomsRefreshRef.current = lastUpdated;
    void refreshRuntimeRoomsFirstPage().catch(() => undefined);
  }, [lastUpdated, refreshRuntimeRoomsFirstPage]);

  const selectedOverviews = useMemo(() => {
    return visibleBotIds
      .map((agentId) => overviews[agentId])
      .filter((item): item is RuntimeOverview => Boolean(item));
  }, [overviews, visibleBotIds]);

  const roomRows = useMemo(
    () =>
      mergePaginatedItems(
        runtimeRoomsQuery.data?.pages,
        (row) => `${row.agentId}:${row.taskId}:${row.source}`,
      ),
    [runtimeRoomsQuery.data],
  );
  const loadMoreRuntimeRooms = useCallback(() => {
    if (!runtimeRoomsQuery.hasNextPage || runtimeRoomsQuery.isFetchingNextPage) return;
    void runtimeRoomsQuery.fetchNextPage();
  }, [runtimeRoomsQuery]);

  const totals = useMemo(
    () => ({
      active: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.active_environments ?? 0),
        0,
      ),
      retained: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.retained_environments ?? 0),
        0,
      ),
      recovery: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.recovery_backlog ?? 0),
        0,
      ),
      cleanup: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.cleanup_backlog ?? 0),
        0,
      ),
    }),
    [selectedOverviews],
  );

  const incidentEntries = useMemo(
    () =>
      selectedOverviews.flatMap((overview) =>
        overview.incidents.map((incident) => ({
          agentId: overview.agentId,
          agentLabel: overview.agentLabel,
          incident,
        })),
      ),
    [selectedOverviews],
  );

  const liveAgents = selectedOverviews.filter(
    (overview) =>
      Boolean(connected[overview.agentId]) ||
      ["available", "partial"].includes(overview.availability.runtime),
  ).length;
  const attentionCount = totals.recovery + totals.cleanup + incidentEntries.length;
  useEffect(() => {
    if (!error || lastErrorToastRef.current === error) return;
    lastErrorToastRef.current = error;
    if (isSilentRuntimeAvailabilityNotice(error)) {
      logSilentRuntimeNotice("error", { message: error });
      return;
    }
    showToast(error, "error", { id: "runtime-overview:error" });
  }, [error, showToast]);

  useEffect(() => {
    const nextKeys = new Set<string>();
    for (const entry of incidentEntries) {
      const key = `${entry.agentId}:${entry.incident}`;
      nextKeys.add(key);
      if (incidentToastKeysRef.current.has(key)) continue;
      if (isSilentRuntimeAvailabilityNotice(entry.incident)) {
        logSilentRuntimeNotice("incident", {
          agentId: entry.agentId,
          agentLabel: entry.agentLabel,
          message: entry.incident,
        });
        continue;
      }
      showToast(`${entry.agentLabel} · ${entry.incident}`, "warning", {
        id: `runtime-overview:incident:${key}`,
      });
    }
    incidentToastKeysRef.current = nextKeys;
  }, [incidentEntries, showToast]);

  if (loading && selectedOverviews.length === 0) {
    return <RuntimeOverviewSkeleton />;
  }

  const tourVariant =
    error
      ? "unavailable"
      : loading && selectedOverviews.length === 0
        ? "loading"
        : selectedOverviews.length === 0
          ? "empty"
          : "default";

  const filterItems = [
    { id: "all", label: t("runtime.overview.filters.all") },
    { id: "active", label: t("runtime.overview.filters.active") },
    { id: "retained", label: t("runtime.overview.filters.retained") },
    { id: "recovery", label: t("runtime.overview.filters.recovery") },
  ];
  const searchLoading =
    searchState.isSearching ||
    (runtimeRoomsQuery.isFetching &&
      !runtimeRoomsQuery.isFetchingNextPage &&
      search.trim() === debouncedSearch);

  return (
    <div
      className="runtime-shell space-y-6"
      data-testid="runtime-overview-screen"
      {...tourRoute("runtime", tourVariant)}
    >
      {/* Header */}
      <div
        className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
        {...tourAnchor("runtime.header")}
      >
        <div className="min-w-0">
          <p className="eyebrow">{t("runtime.overview.title")}</p>
          <h1 className="m-0 mt-1 text-[1.375rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            {t("runtime.controlCard.title", undefined)}
          </h1>
        </div>

        <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto lg:justify-end">
          <div className="w-full sm:w-[220px]" {...tourAnchor("runtime.agent-switcher")}>
            <AgentSwitcher
              multiple
              singleRow
              fullWidth
              selectedBotIds={selectedBotIds}
              onSelectionChange={setSelectedBotIds}
              className="agent-switcher--compact"
            />
          </div>

          <div className="w-full sm:w-auto" {...tourAnchor("runtime.search")}>
            <PageSearchField
              className="w-full sm:w-64 xl:w-64"
              value={search}
              onChange={setSearch}
              placeholder={t("runtime.overview.searchPlaceholder")}
              loading={searchLoading}
              loadingLabel={t("runtime.overview.searching", undefined)}
              clearLabel={t("common.clear", undefined)}
            />
          </div>

          <div {...tourAnchor("runtime.filters")}>
            <SoftTabs
              items={filterItems}
              value={statusFilter}
              onChange={(id) => setStatusFilter(id as RuntimeRoomFilter)}
              ariaLabel={t("runtime.overview.filterLabel")}
            />
          </div>
        </div>
      </div>

      {/* Metric strip */}
      <div {...tourAnchor("runtime.metrics")}>
        <PageMetricStrip>
          <PageMetricStripItem
            label={t("runtime.overview.metrics.onlineAgents")}
            value={`${liveAgents}/${selectedOverviews.length || 0}`}
            hint={t("runtime.overview.metrics.onlineAgentsHint")}
          />
          <PageMetricStripItem
            label={t("runtime.overview.metrics.executions")}
            value={String(totals.active)}
            tone={totals.active > 0 ? "accent" : "neutral"}
            hint={t("runtime.overview.metrics.executionsHint")}
          />
          <PageMetricStripItem
            label={t("runtime.overview.filters.retained")}
            value={String(totals.retained)}
            tone={totals.retained > 0 ? "success" : "neutral"}
          />
          <PageMetricStripItem
            label={t("runtime.overview.metrics.attention")}
            value={String(attentionCount)}
            tone={attentionCount > 0 ? "warning" : "neutral"}
            hint={t("runtime.overview.metrics.attentionHint")}
          />
        </PageMetricStrip>
      </div>

      {/* Main grid */}
      <div>
        <section className="overflow-hidden rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)]">
          <header className="flex items-baseline justify-between gap-3 border-b border-[var(--divider-hair)] px-3 py-2.5">
            <div className="min-w-0">
              <p className="eyebrow truncate">{translate("generated.runtime.runtime_5359aeee")}</p>
              <h3 className="m-0 mt-1 truncate text-[var(--font-size-sm)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
                {t("runtime.overview.liveExecutions")}
              </h3>
            </div>
            <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
              {roomRows.length}
            </span>
          </header>

          <div data-testid="runtime-live-list">
            <div className="max-h-[520px] min-h-[280px] overflow-auto overscroll-contain lg:max-h-[calc(100vh-24rem)]">
              <div className="min-w-[910px]">
                <div
                  className={cn(
                    "sticky top-0 z-10 grid items-center gap-4 border-b border-[var(--divider-hair)] bg-[var(--panel)] px-3 py-2",
                    liveTableColumns,
                  )}
                >
                  <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    {t("runtime.overview.table.agent", undefined)}
                  </span>
                  <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    {t("runtime.overview.table.task", undefined)}
                  </span>
                  <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    {t("common.status")}
                  </span>
                  <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    {t("runtime.overview.table.source", undefined)}
                  </span>
                  <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    {t("runtime.overview.table.summary", undefined)}
                  </span>
                  <span
                    className={cn(
                      liveTablePinnedColumn,
                      "z-20 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]",
                    )}
                  >
                    {t("runtime.overview.table.updated", undefined)}
                  </span>
                </div>

                <div>
                  {roomRows.length === 0 ? (
                    <div
                      className="flex min-h-[240px] flex-col items-center justify-center gap-2 px-3 py-10 text-center text-[0.8125rem] text-[var(--text-tertiary)]"
                      {...tourAnchor("runtime.empty-live")}
                    >
                      <Activity className="h-4 w-4 text-[var(--text-quaternary)]" />
                      <p className="m-0">{t("runtime.overview.noExecutionsMatch")}</p>
                    </div>
                  ) : (
                    roomRows.map((row) => (
                      <LiveRow
                        key={`${row.agentId}-${row.taskId}-${row.source}`}
                        row={row}
                      />
                    ))
                  )}
                  <InfiniteListFooter
                    hasMore={Boolean(runtimeRoomsQuery.hasNextPage)}
                    loading={runtimeRoomsQuery.isFetchingNextPage}
                    onLoadMore={loadMoreRuntimeRooms}
                    label={t("common.loadMore", undefined)}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
