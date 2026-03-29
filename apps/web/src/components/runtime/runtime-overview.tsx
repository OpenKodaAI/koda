"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Bot,
  Search,
} from "lucide-react";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveBotSelection } from "@/lib/bot-selection";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import {
  buildRuntimeRoomRows,
  getRuntimeRowSummary,
  matchesRuntimeRoomFilter,
  type RuntimeRoomFilter,
  type RuntimeRoomRow,
} from "@/lib/runtime-overview-model";
import type { RuntimeOverview } from "@/lib/runtime-types";
import { getRuntimeLabel, getRuntimeTone } from "@/lib/runtime-ui";
import { getSemanticStyle, getSemanticTextStyle } from "@/lib/theme-semantic";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";

function RuntimeOverviewSkeleton() {
  return (
    <div className="runtime-shell runtime-shell--wide space-y-5" data-testid="runtime-overview-skeleton" {...tourRoute("runtime", "loading")}>
      <div className="runtime-toolbar runtime-toolbar--standard" {...tourAnchor("runtime.header")}>
        <div className="runtime-toolbar__controls">
          <div className="skeleton h-11 w-full rounded-xl" />
          <div className="app-search">
            <div className="skeleton-circle h-4 w-4" />
            <div className="skeleton h-4 w-56 rounded-xl" />
          </div>
          <div className="runtime-filter-row">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="skeleton h-9 w-24 rounded-full" />
            ))}
          </div>
          <div className="skeleton h-7 w-20 rounded-full justify-self-start lg:justify-self-end" />
        </div>
      </div>

      <div className="metric-strip">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="metric-strip__item">
            <div className="skeleton h-3 w-20 rounded-xl" />
            <div className="mt-2 skeleton h-6 w-16 rounded-xl" />
          </div>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_300px]">
        <div className="runtime-panel runtime-panel--dense min-h-[420px]">
          <div className="runtime-panel__header">
            <div className="skeleton h-4 w-32 rounded-xl" />
          </div>
          <div className="runtime-live-list">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="runtime-live-row">
                <div className="runtime-live-row__main">
                  <div className="skeleton-circle h-2.5 w-2.5" />
                  <div className="skeleton h-3 w-20 rounded-xl" />
                  <div className="skeleton h-3 w-12 rounded-xl" />
                  <div className="skeleton h-6 w-20 rounded-full" />
                  <div className="skeleton h-3 w-[40%] rounded-xl" />
                </div>
                <div className="runtime-live-row__side">
                  <div className="skeleton h-3 w-12 rounded-xl" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="runtime-panel runtime-panel--dense min-h-[420px]">
          <div className="runtime-panel__header">
            <div className="skeleton h-4 w-16 rounded-xl" />
          </div>
          <div className="runtime-bot-rail">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="runtime-bot-row">
                <div className="runtime-bot-row__identity">
                  <div className="skeleton-circle h-2.5 w-2.5" />
                  <div className="skeleton h-3 w-24 rounded-xl" />
                </div>
                <div className="flex items-center gap-3">
                  <div className="skeleton h-3 w-14 rounded-xl" />
                  <div className="skeleton h-3 w-12 rounded-xl" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function InlineAlert({
  children,
  tone = "warning",
}: {
  children: React.ReactNode;
  tone?: "warning" | "danger";
}) {
  return (
    <div
      className={cn(
        "runtime-inline-alert",
        tone === "danger" && "runtime-inline-alert--danger"
      )}
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function LiveRow({ row }: { row: RuntimeRoomRow }) {
  const { t } = useAppI18n();
  const botColor = getBotColor(row.botId);
  const summary = truncateText(getRuntimeRowSummary(row), 120);

  return (
    <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <Link
        href={`/runtime/${row.botId}/tasks/${row.taskId}`}
        className="runtime-live-row group"
      >
        <div className="runtime-live-row__main">
          <span className="runtime-inline-dot" style={{ backgroundColor: botColor }} />
          <span className="runtime-inline-id">{getBotLabel(row.botId)}</span>
          <span className="runtime-inline-id">#{row.taskId}</span>
          <span
            className="runtime-inline-tone"
            style={getSemanticStyle(getRuntimeTone(row.phase))}
          >
            {getRuntimeLabel(row.phase)}
          </span>
          <p className="runtime-live-row__title">{summary}</p>
        </div>
        <div className="runtime-live-row__side">
          <span className="runtime-live-row__time">
            {row.updatedAt ? formatRelativeTime(row.updatedAt) : t("common.now")}
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

function BotRailRow({
  overview,
  live,
}: {
  overview: RuntimeOverview;
  live: boolean;
}) {
  const { t } = useAppI18n();
  const activeCount = overview.snapshot?.active_environments ?? 0;
  const attentionCount =
    (overview.snapshot?.recovery_backlog ?? 0) +
    (overview.snapshot?.cleanup_backlog ?? 0) +
    overview.incidents.length;
  const retainedCount = overview.snapshot?.retained_environments ?? 0;
  const runtimeTone = live ? "info" : getRuntimeTone(overview.availability.runtime);

  return (
    <div className="runtime-bot-row">
      <div className="runtime-bot-row__identity">
        <span className="runtime-inline-dot" style={{ backgroundColor: overview.botColor }} />
        <span className="runtime-bot-row__name">{overview.botLabel}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="runtime-bot-row__state" style={getSemanticTextStyle(runtimeTone)}>
          {live ? t("runtime.overview.live") : getRuntimeLabel(overview.availability.runtime)}
        </span>
        <span className="runtime-live-row__time">{activeCount}/{retainedCount}/{attentionCount}</span>
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
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>(initialBotIds ?? []);
  const [statusFilter, setStatusFilter] = useState<RuntimeRoomFilter>("all");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const { overviews, loading, connected, error } =
    useRuntimeOverview(selectedBotIds);

  const selectedOverviews = useMemo(() => {
    return visibleBotIds
      .map((botId) => overviews[botId])
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
        getBotLabel(row.botId),
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
        0
      ),
      retained: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.retained_environments ?? 0),
        0
      ),
      recovery: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.recovery_backlog ?? 0),
        0
      ),
      cleanup: selectedOverviews.reduce(
        (sum, overview) => sum + (overview.snapshot?.cleanup_backlog ?? 0),
        0
      ),
    }),
    [selectedOverviews]
  );

  const incidentEntries = useMemo(
    () =>
      selectedOverviews.flatMap((overview) =>
        overview.incidents.map((incident) => ({
          botId: overview.botId,
          botLabel: overview.botLabel,
          incident,
        }))
      ),
    [selectedOverviews]
  );

  const liveBots = selectedOverviews.filter(
    (overview) =>
      Boolean(connected[overview.botId]) ||
      ["available", "partial"].includes(overview.availability.runtime)
  ).length;
  const attentionCount = totals.recovery + totals.cleanup + incidentEntries.length;
  const visibleRows = roomRows.slice(0, 10);

  if (loading && selectedOverviews.length === 0) {
    return <RuntimeOverviewSkeleton />;
  }

  const tourVariant =
    error ? "unavailable" : loading && selectedOverviews.length === 0 ? "loading" : selectedOverviews.length === 0 ? "empty" : "default";

  return (
    <div className="runtime-shell runtime-shell--wide space-y-5" data-testid="runtime-overview-screen" {...tourRoute("runtime", tourVariant)}>
      <div className="runtime-toolbar runtime-toolbar--standard" {...tourAnchor("runtime.header")}>
        <div className="runtime-toolbar__controls">
          <div className="runtime-toolbar__bot" {...tourAnchor("runtime.bot-switcher")}>
            <BotSwitcher
              multiple
              selectedBotIds={selectedBotIds}
              onSelectionChange={setSelectedBotIds}
            />
          </div>

          <label className="app-search runtime-search runtime-search--field" {...tourAnchor("runtime.search")}>
            <Search className="h-4 w-4 text-[var(--text-quaternary)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("runtime.overview.searchPlaceholder")}
              className="runtime-search__input"
            />
          </label>

          <div className="runtime-filter-row" role="tablist" aria-label={t("runtime.overview.filterLabel")} {...tourAnchor("runtime.filters")}>
            {[
              { value: "all", label: t("runtime.overview.filters.all") },
              { value: "active", label: t("runtime.overview.filters.active") },
              { value: "retained", label: t("runtime.overview.filters.retained") },
              { value: "recovery", label: t("runtime.overview.filters.recovery") },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setStatusFilter(item.value as RuntimeRoomFilter)}
                className={cn(
                  "runtime-filter-pill",
                  statusFilter === item.value && "is-active"
                )}
                aria-pressed={statusFilter === item.value}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="metric-strip" {...tourAnchor("runtime.metrics")}>
        <div className="metric-strip__item">
          <span className="metric-label">{t("runtime.overview.metrics.onlineBots")}</span>
          <span className="metric-value">{`${liveBots}/${selectedOverviews.length || 0}`}</span>
        </div>
        <div className="metric-strip__item">
          <span className="metric-label">{t("runtime.overview.metrics.executions")}</span>
          <span className="metric-value">{String(totals.active)}</span>
        </div>
        <div className="metric-strip__item">
          <span className="metric-label">{t("runtime.overview.metrics.attention")}</span>
          <span className={cn("metric-value", attentionCount > 0 && "metric-value--accent")}>{String(attentionCount)}</span>
        </div>
      </div>

      {error ? (
        <InlineAlert tone="danger">{error}</InlineAlert>
      ) : null}

      {incidentEntries.slice(0, 2).map((entry) => (
        <InlineAlert key={`${entry.botId}-${entry.incident}`}>
          <span className="font-semibold text-[var(--text-primary)]">{entry.botLabel}</span>
          <span className="mx-2 text-[var(--text-quaternary)]">•</span>
          <span className="text-[var(--text-secondary)]">{entry.incident}</span>
        </InlineAlert>
      ))}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_300px]">
        <section className="runtime-panel runtime-panel--dense">
          <div className="runtime-panel__header">
            <p className="runtime-panel__title">{t("runtime.overview.liveExecutions")}</p>
          </div>

          <div className="runtime-live-list" data-testid="runtime-live-list">
            {visibleRows.length === 0 ? (
              <div className="runtime-empty" {...tourAnchor("runtime.empty-live")}>
                <Activity className="h-5 w-5" />
                <p>{t("runtime.overview.noExecutionsMatch")}</p>
              </div>
            ) : (
              visibleRows.map((row) => (
                <LiveRow key={`${row.botId}-${row.taskId}-${row.source}`} row={row} />
              ))
            )}
          </div>
        </section>

        <aside className="runtime-panel runtime-panel--dense">
          <div className="runtime-panel__header">
            <p className="runtime-panel__title">{t("runtime.overview.bots")}</p>
          </div>

          <div className="runtime-bot-rail">
            {selectedOverviews.length === 0 ? (
              <div className="runtime-empty" {...tourAnchor("runtime.empty-bots")}>
                <Bot className="h-5 w-5" />
                <p>{t("runtime.overview.noVisibleBots")}</p>
              </div>
            ) : (
              selectedOverviews.map((overview) => (
                <BotRailRow
                  key={overview.botId}
                  overview={overview}
                  live={Boolean(connected[overview.botId])}
                />
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
