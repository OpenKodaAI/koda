"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { Activity, Bot as AgentIcon, Search } from "lucide-react";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { AgentGlyph } from "@/components/dashboard/agent-glyph";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveAgentSelection } from "@/lib/agent-selection";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import {
  buildRuntimeRoomRows,
  getRuntimeRowSummary,
  matchesRuntimeRoomFilter,
  type RuntimeRoomFilter,
  type RuntimeRoomRow,
} from "@/lib/runtime-overview-model";
import type { RuntimeOverview } from "@/lib/runtime-types";
import { getRuntimeLabel, getRuntimeTone } from "@/lib/runtime-ui";
import type { SemanticTone } from "@/lib/theme-semantic";
import { InlineAlert } from "@/components/ui/inline-alert";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import {
  PageMetricStrip,
  PageMetricStripItem,
} from "@/components/ui/page-primitives";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";

function toneToStatusDot(tone: SemanticTone): StatusDotTone {
  if (tone === "success" || tone === "info" || tone === "warning" || tone === "danger" || tone === "retry" || tone === "neutral") {
    return tone;
  }
  return "neutral";
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

      <div className="metric-strip">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="metric-strip__item">
            <div className="skeleton h-3 w-20 rounded" />
            <div className="skeleton mt-2 h-6 w-16 rounded" />
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_320px]">
        <section className="min-h-[360px] space-y-2">
          <div className="skeleton h-4 w-32 rounded" />
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="skeleton h-10 w-full rounded" />
          ))}
        </section>
        <aside className="min-h-[360px] space-y-2">
          <div className="skeleton h-4 w-16 rounded" />
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton h-10 w-full rounded" />
          ))}
        </aside>
      </div>
    </div>
  );
}

function LiveRow({ row, index }: { row: RuntimeRoomRow; index: number }) {
  const { t } = useAppI18n();
  const agentColor = getAgentColor(row.agentId);
  const summary = truncateText(getRuntimeRowSummary(row), 120);
  const phaseTone = toneToStatusDot(getRuntimeTone(row.phase));
  const phaseLabel = getRuntimeLabel(row.phase);
  const isLive = phaseTone === "info" || phaseTone === "warning";

  return (
    <Link
      href={`/runtime/${row.agentId}/tasks/${row.taskId}`}
      className={cn(
        "group grid w-full gap-4 px-3 py-3 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "grid-cols-[auto_auto_auto_1fr_auto] items-center",
        "hover:bg-[var(--hover-tint)] focus-visible:bg-[var(--hover-tint)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] rounded-[var(--radius-panel-sm)]",
        index > 0 && "border-t border-[color:var(--divider-hair)]",
      )}
    >
      <StatusDot color={agentColor} />
      <span className="font-mono text-[0.75rem] text-[var(--text-secondary)]">
        {getAgentLabel(row.agentId)}
      </span>
      <span className="font-mono text-[0.75rem] text-[var(--text-quaternary)]">
        #{row.taskId}
      </span>
      <span className="flex min-w-0 items-center gap-2">
        <StatusDot tone={phaseTone} pulse={isLive} />
        <span className="text-[0.75rem] text-[var(--text-tertiary)]">{phaseLabel}</span>
        <span className="mx-1 text-[var(--text-quaternary)]">·</span>
        <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">{summary}</span>
      </span>
      <span className="whitespace-nowrap text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
        {row.updatedAt ? formatRelativeTime(row.updatedAt) : t("common.now")}
      </span>
    </Link>
  );
}

function AgentRailRow({
  overview,
  live,
  index,
}: {
  overview: RuntimeOverview;
  live: boolean;
  index: number;
}) {
  const { t } = useAppI18n();
  const activeCount = overview.snapshot?.active_environments ?? 0;
  const attentionCount =
    (overview.snapshot?.recovery_backlog ?? 0) +
    (overview.snapshot?.cleanup_backlog ?? 0) +
    overview.incidents.length;
  const retainedCount = overview.snapshot?.retained_environments ?? 0;
  const runtimeTone = toneToStatusDot(
    live ? "info" : getRuntimeTone(overview.availability.runtime),
  );
  const label = live ? t("runtime.overview.live") : getRuntimeLabel(overview.availability.runtime);

  return (
    <div
      className={cn(
        "grid items-center gap-3 px-3 py-2.5",
        "grid-cols-[auto_1fr_auto]",
        index > 0 && "border-t border-[color:var(--divider-hair)]",
      )}
    >
      <AgentGlyph
        agentId={overview.agentId}
        color={overview.agentColor}
        variant="list"
        shape="swatch"
        className="h-6 w-6 shrink-0"
      />
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
          {overview.agentLabel}
        </span>
        <StatusDot tone={runtimeTone} pulse={live} />
        <span className="text-[0.6875rem] text-[var(--text-tertiary)]">{label}</span>
      </div>
      <span className="font-mono text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
        {activeCount}·{retainedCount}·{attentionCount}
      </span>
    </div>
  );
}

export function RuntimeOverviewScreen({
  initialBotIds,
}: {
  initialBotIds?: string[];
}) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>(initialBotIds ?? []);
  const [statusFilter, setStatusFilter] = useState<RuntimeRoomFilter>("all");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds],
  );
  const { overviews, loading, connected, error } = useRuntimeOverview(selectedBotIds);

  const selectedOverviews = useMemo(() => {
    return visibleBotIds
      .map((agentId) => overviews[agentId])
      .filter((item): item is RuntimeOverview => Boolean(item));
  }, [overviews, visibleBotIds]);

  const roomRows = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    return buildRuntimeRoomRows(selectedOverviews).filter((row) => {
      if (!matchesRuntimeRoomFilter(row, statusFilter)) return false;
      if (!query) return true;

      const haystack = [
        row.queryText,
        row.queue?.query_text,
        row.environment?.branch_name,
        row.environment?.workspace_path,
        getAgentLabel(row.agentId),
        row.phase,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return haystack.includes(query);
    });
  }, [deferredSearch, selectedOverviews, statusFilter]);

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
  const visibleRows = roomRows.slice(0, 10);

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

  return (
    <div
      className="runtime-shell space-y-6"
      data-testid="runtime-overview-screen"
      {...tourRoute("runtime", tourVariant)}
    >
      {/* Header */}
      <div
        className="flex flex-wrap items-center justify-between gap-3"
        {...tourAnchor("runtime.header")}
      >
        <div className="w-[200px]" {...tourAnchor("runtime.agent-switcher")}>
          <AgentSwitcher
            multiple
            singleRow
            selectedBotIds={selectedBotIds}
            onSelectionChange={setSelectedBotIds}
            className="agent-switcher--compact"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label
            className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-primary)] transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] focus-within:border-[var(--accent)]"
            {...tourAnchor("runtime.search")}
          >
            <Search className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("runtime.overview.searchPlaceholder")}
              className="w-44 bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
            />
          </label>

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
            label={t("runtime.overview.metrics.attention")}
            value={String(attentionCount)}
            tone={attentionCount > 0 ? "warning" : "neutral"}
            hint={t("runtime.overview.metrics.attentionHint")}
          />
        </PageMetricStrip>
      </div>

      {/* Alerts */}
      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      {incidentEntries.slice(0, 2).map((entry) => (
        <InlineAlert key={`${entry.agentId}-${entry.incident}`} tone="warning">
          <span className="font-semibold text-[var(--text-primary)]">{entry.agentLabel}</span>
          <span className="mx-2 text-[var(--text-quaternary)]">·</span>
          <span>{entry.incident}</span>
        </InlineAlert>
      ))}

      {/* Main grid */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_320px]">
        <section>
          <header className="mb-2 flex items-baseline justify-between px-3">
            <h3 className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {t("runtime.overview.liveExecutions")}
            </h3>
            <span className="eyebrow">
              {visibleRows.length} / {roomRows.length}
            </span>
          </header>

          <div
            className="flex flex-col"
            data-testid="runtime-live-list"
          >
            {visibleRows.length === 0 ? (
              <div
                className="flex flex-col items-center gap-2 py-10 text-center text-[0.8125rem] text-[var(--text-tertiary)]"
                {...tourAnchor("runtime.empty-live")}
              >
                <Activity className="h-4 w-4 text-[var(--text-quaternary)]" />
                <p className="m-0">{t("runtime.overview.noExecutionsMatch")}</p>
              </div>
            ) : (
              visibleRows.map((row, index) => (
                <LiveRow
                  key={`${row.agentId}-${row.taskId}-${row.source}`}
                  row={row}
                  index={index}
                />
              ))
            )}
          </div>
        </section>

        <aside>
          <header className="mb-2 flex items-baseline justify-between px-3">
            <h3 className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {t("runtime.overview.agents")}
            </h3>
            <span className="eyebrow">{liveAgents}/{selectedOverviews.length || 0}</span>
          </header>

          <div className="flex flex-col">
            {selectedOverviews.length === 0 ? (
              <div
                className="flex flex-col items-center gap-2 py-10 text-center text-[0.8125rem] text-[var(--text-tertiary)]"
                {...tourAnchor("runtime.empty-agents")}
              >
                <AgentIcon className="h-4 w-4 text-[var(--text-quaternary)]" />
                <p className="m-0">{t("runtime.overview.noVisibleAgents")}</p>
              </div>
            ) : (
              selectedOverviews.map((overview, index) => (
                <AgentRailRow
                  key={overview.agentId}
                  overview={overview}
                  live={Boolean(connected[overview.agentId])}
                  index={index}
                />
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
