"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Bot as AgentIcon, Search } from "lucide-react";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
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
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import {
  PageMetricStrip,
  PageMetricStripItem,
} from "@/components/ui/page-primitives";
import { AnimatedCardStatusList, type Card as StatusCard } from "@/components/ui/card-status-list";
import { useToast } from "@/hooks/use-toast";
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
        "group grid w-full gap-x-3 gap-y-1.5 px-3 py-3 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "grid-cols-[auto_1fr_auto] items-center sm:grid-cols-[auto_auto_auto_1fr_auto]",
        "hover:bg-[var(--hover-tint)] focus-visible:bg-[var(--hover-tint)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] rounded-[var(--radius-panel-sm)]",
        index > 0 && "border-t border-[color:var(--divider-hair)]",
      )}
    >
      <StatusDot color={agentColor} />
      <span className="hidden font-mono text-[0.75rem] text-[var(--text-secondary)] sm:inline">
        {getAgentLabel(row.agentId)}
      </span>
      <span className="hidden font-mono text-[0.75rem] text-[var(--text-quaternary)] sm:inline">
        #{row.taskId}
      </span>
      <span className="flex min-w-0 items-center gap-2">
        <span className="font-mono text-[0.75rem] text-[var(--text-secondary)] sm:hidden">
          {getAgentLabel(row.agentId)} #{row.taskId}
        </span>
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

function RuntimeLayerPill({
  label,
  status,
}: {
  label: string;
  status: string;
}) {
  const tone: StatusDotTone =
    status === "available"
      ? "success"
      : status === "partial" || status === "unknown"
        ? "warning"
        : status === "unavailable" || status === "offline" || status === "disabled"
          ? "danger"
          : toneToStatusDot(getRuntimeTone(status));
  return (
    <span
      className="inline-flex min-w-0 items-center gap-1.5 rounded-[var(--radius-chip)] bg-[var(--panel-soft)] px-2 py-1 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-tertiary)]"
      title={`${label}: ${getRuntimeLabel(status)}`}
    >
      <StatusDot tone={tone} />
      <span>{label}</span>
    </span>
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
  const layers = [
    { label: "RT", status: overview.availability.runtime },
    { label: "DB", status: overview.availability.database },
    { label: "BR", status: overview.availability.browser },
    { label: "AT", status: overview.availability.attach },
  ];

  return (
    <div
      className={cn(
        "grid items-start gap-3 px-3 py-3",
        "grid-cols-[auto_1fr]",
        index > 0 && "border-t border-[color:var(--divider-hair)]",
      )}
    >
      <AgentSigil
        agentId={overview.agentId}
        label={overview.agentLabel}
        color={overview.agentColor}
        status={live ? "running" : undefined}
        size="xs"
      />
      <div className="flex min-w-0 items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
              {overview.agentLabel}
            </span>
            <StatusDot tone={runtimeTone} pulse={live} />
            <span className="text-[0.6875rem] text-[var(--text-tertiary)]">{label}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {layers.map((item) => (
              <RuntimeLayerPill key={item.label} label={item.label} status={item.status} />
            ))}
          </div>
        </div>
        <span className="shrink-0 font-mono text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
          {activeCount}·{retainedCount}·{attentionCount}
        </span>
      </div>
    </div>
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
  const incidentToastKeysRef = useRef<Set<string>>(new Set());
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>(initialBotIds ?? []);
  const [statusFilter, setStatusFilter] = useState<RuntimeRoomFilter>("all");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds],
  );
  const { overviews, loading, connected, error, refreshAgent } = useRuntimeOverview(selectedBotIds);

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
  const runtimeStatusCards = useMemo<StatusCard[]>(() => {
    const availabilityIssues = selectedOverviews.reduce((count, overview) => {
      const availability = overview.availability;
      return count + [availability.runtime, availability.database, availability.browser, availability.attach]
        .filter((status) => !["available", "active"].includes(status)).length;
    }, 0);
    return [
      {
        id: "live-executions",
        title: totals.active > 0
          ? `${totals.active} active execution${totals.active === 1 ? "" : "s"}`
          : "No active execution rooms",
        status: totals.active > 0 ? "syncing" : "completed",
      },
      {
        id: "runtime-agents",
        title: `${liveAgents}/${selectedOverviews.length || 0} agents online`,
        status:
          selectedOverviews.length > 0 && liveAgents === selectedOverviews.length
            ? "completed"
            : "updates-found",
      },
      {
        id: "recovery-backlog",
        title: `${totals.recovery} recovery · ${totals.cleanup} cleanup backlog`,
        status: totals.recovery + totals.cleanup > 0 ? "updates-found" : "completed",
      },
      {
        id: "incident-review",
        title: `${incidentEntries.length} incident${incidentEntries.length === 1 ? "" : "s"} to review`,
        status: incidentEntries.length > 0 ? "updates-found" : "completed",
      },
      {
        id: "runtime-layers",
        title: availabilityIssues > 0
          ? `${availabilityIssues} runtime layer issue${availabilityIssues === 1 ? "" : "s"}`
          : "Runtime layers healthy",
        status: availabilityIssues > 0 ? "updates-found" : "completed",
      },
    ];
  }, [
    incidentEntries.length,
    liveAgents,
    selectedOverviews,
    totals.active,
    totals.cleanup,
    totals.recovery,
  ]);

  const refreshRuntimeStatus = async () => {
    await Promise.all(visibleBotIds.map((agentId) => refreshAgent(agentId)));
    showToast(t("runtime.overview.refreshQueued", { defaultValue: "Runtime status refreshed." }), "success");
  };

  useEffect(() => {
    if (!error || lastErrorToastRef.current === error) return;
    lastErrorToastRef.current = error;
    showToast(error, "error", { id: "runtime-overview:error" });
  }, [error, showToast]);

  useEffect(() => {
    const nextKeys = new Set<string>();
    for (const entry of incidentEntries) {
      const key = `${entry.agentId}:${entry.incident}`;
      nextKeys.add(key);
      if (incidentToastKeysRef.current.has(key)) continue;
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
            {t("runtime.controlCard.title", { defaultValue: "Runtime operations" })}
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

          <label
            className="inline-flex h-9 w-full items-center gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-primary)] transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] focus-within:border-[var(--accent)] sm:w-auto"
            {...tourAnchor("runtime.search")}
          >
            <Search className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("runtime.overview.searchPlaceholder")}
              className="w-full bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)] sm:w-44"
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

        <aside className="space-y-4">
          <AnimatedCardStatusList
            title={t("runtime.overview.statusRail", { defaultValue: "Runtime status" })}
            cards={runtimeStatusCards}
            sort="attention-first"
            synchronizeLabel={t("common.refresh", { defaultValue: "Refresh" })}
            onSynchronize={() => {
              void refreshRuntimeStatus();
            }}
          />

          <section>
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
          </section>
        </aside>
      </div>
    </div>
  );
}
