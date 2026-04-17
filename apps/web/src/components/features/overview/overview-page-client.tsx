"use client";


import dynamic from "next/dynamic";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BookOpen,
  CalendarPlus,
  Play,
  Sparkles,
} from "lucide-react";
import { ActivityHeatmap } from "@/components/dashboard/activity-heatmap";
import {
  ExecutionHistory,
  type ExecutionHistoryStrings,
} from "@/components/dashboard/execution-history";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { OverviewComposer } from "@/components/features/overview/overview-composer";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useDailyActivity } from "@/hooks/use-daily-activity";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useBotStats } from "@/hooks/use-bot-stats";
import { resolveBotSelection } from "@/lib/bot-selection";
import type { BotStats } from "@/lib/types";

const BotDetailModal = dynamic(
  () =>
    import("@/components/bots/bot-detail-modal").then((module) => ({
      default: module.BotDetailModal,
    })),
  { loading: () => null },
);

function OverviewSkeleton() {
  return (
    <div className="space-y-4" {...tourRoute("overview", "loading")}>
      {/* BotSwitcher placeholder */}
      <div className="max-w-[350px]" {...tourAnchor("overview.bot-switcher")}>
        <div className="skeleton h-11 w-full rounded-xl" />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" {...tourAnchor("overview.stats")}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="glass-card-sm p-5">
            <div className="skeleton skeleton-text mb-3" style={{ width: "40%" }} />
            <div className="skeleton skeleton-heading mb-2" style={{ width: "50%" }} />
            <div className="skeleton skeleton-text" style={{ width: "65%" }} />
          </div>
        ))}
      </div>

      {/* Activity + Cost charts */}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="app-section min-h-[340px] p-5 sm:p-6" />
        <div className="app-section min-h-[340px] p-5 sm:p-6" />
      </div>

      {/* Live Plan */}
      <div className="app-section min-h-[220px] p-5 sm:p-6 lg:p-7" />
    </div>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<OverviewPageFallback />}>
      <OverviewPageContent />
    </Suspense>
  );
}

function OverviewPageFallback() {
  return (
    <div className="space-y-4" {...tourRoute("overview", "loading")}>
      <div className="max-w-[350px]" {...tourAnchor("overview.bot-switcher")}>
        <BotSwitcher
          multiple
          selectedBotIds={[]}
          onSelectionChange={() => undefined}
        />
      </div>
      <OverviewSkeleton />
    </div>
  );
}

function OverviewPageContent() {
  const { t } = useAppI18n();
  const { bots, botDisplayMap } = useBotCatalog();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const {
    stats: allStats,
    loading,
  } = useBotStats();

  const modalBotId = useMemo(() => {
    const bot = searchParams.get("bot");
    return bot && botDisplayMap[bot] ? bot : null;
  }, [botDisplayMap, searchParams]);

  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );

  const statsByBot = useMemo(
    () => {
      const statsMap = Object.fromEntries(
        (allStats ?? []).map((stats) => [stats.botId, stats]),
      ) as Record<string, BotStats>;
      return bots.map((bot) => ({
        bot,
        stats: statsMap[bot.id],
      }));
    },
    [allStats, bots],
  );

  const visibleEntries = useMemo(
    () =>
      statsByBot.filter((entry) => visibleBotIds.includes(entry.bot.id)),
    [statsByBot, visibleBotIds]
  );

  // TEMP: mock roster data for design review — remove once real bots exist.
  const [rosterMockEntries] = useState(() => {
    const now = Date.now();
    const iso = (minutesAgo: number) => new Date(now - minutesAgo * 60_000).toISOString();
    let taskSeed = 1000;
    const nextTaskId = () => {
      taskSeed += 1;
      return taskSeed;
    };
    const mockTask = (overrides: Partial<import("@/lib/types").Task>): import("@/lib/types").Task => ({
      id: nextTaskId(),
      user_id: 1,
      chat_id: 1,
      status: "completed",
      query_text: null,
      model: null,
      work_dir: null,
      attempt: 1,
      max_attempts: 3,
      cost_usd: 0,
      error_message: null,
      created_at: iso(10),
      started_at: null,
      completed_at: null,
      session_id: null,
      ...overrides,
    });
    return [
      {
        bot: { id: "masp", label: "MASP", color: "#6e97d9", colorRgb: "110, 151, 217" },
        stats: {
          botId: "masp",
          totalTasks: 142,
          activeTasks: 2,
          completedTasks: 128,
          failedTasks: 12,
          queuedTasks: 0,
          totalQueries: 412,
          totalCost: 18.24,
          todayCost: 1.64,
          dbExists: true,
          dailyCosts: [],
          recentTasks: [
            mockTask({
              status: "completed",
              query_text: "Summarize yesterday's exhibition visitor feedback and highlight top themes",
              created_at: iso(3),
              started_at: iso(3),
              completed_at: iso(2),
              cost_usd: 0.18,
            }),
            mockTask({
              status: "completed",
              query_text: "Draft newsletter for subscribers — April edition",
              created_at: iso(36),
              completed_at: iso(34),
              cost_usd: 0.11,
            }),
            mockTask({
              status: "failed",
              query_text: "Sync ticketing system backlog for new Picasso exhibition",
              created_at: iso(120),
              completed_at: iso(118),
              error_message: "Upstream timeout",
            }),
          ],
        },
      },
      {
        bot: { id: "air-compass", label: "Air Compass", color: "#5da9a3", colorRgb: "93, 169, 163" },
        stats: {
          botId: "air-compass",
          totalTasks: 89,
          activeTasks: 1,
          completedTasks: 81,
          failedTasks: 7,
          queuedTasks: 0,
          totalQueries: 276,
          totalCost: 9.08,
          todayCost: 0.42,
          dbExists: true,
          dailyCosts: [],
          recentTasks: [
            mockTask({
              status: "completed",
              query_text: "Re-evaluate Guarulhos airport delay signals for the last 6 hours",
              created_at: iso(10),
              started_at: iso(10),
              completed_at: iso(7),
              cost_usd: 0.04,
            }),
            mockTask({
              status: "completed",
              query_text: "Cross-check SBGL METAR with anomaly feed",
              created_at: iso(82),
              completed_at: iso(80),
              cost_usd: 0.03,
            }),
          ],
        },
      },
      {
        bot: { id: "luby", label: "Luby", color: "#c07a96", colorRgb: "192, 122, 150" },
        stats: {
          botId: "luby",
          totalTasks: 54,
          activeTasks: 0,
          completedTasks: 51,
          failedTasks: 3,
          queuedTasks: 1,
          totalQueries: 168,
          totalCost: 5.12,
          todayCost: 0,
          dbExists: true,
          dailyCosts: [],
          recentTasks: [
            mockTask({
              status: "completed",
              query_text: "Prepare weekly CRM digest for sales team — include new qualified leads",
              created_at: iso(22),
              completed_at: iso(20),
              cost_usd: 0.06,
            }),
            mockTask({
              status: "completed",
              query_text: "Tag inactive accounts in the Midwest pipeline",
              created_at: iso(150),
              completed_at: iso(148),
              cost_usd: 0.05,
            }),
          ],
        },
      },
      {
        bot: { id: "archivist", label: "Archivist", color: "#9f8ad5", colorRgb: "159, 138, 213" },
        stats: {
          botId: "archivist",
          totalTasks: 211,
          activeTasks: 0,
          completedTasks: 205,
          failedTasks: 6,
          queuedTasks: 0,
          totalQueries: 633,
          totalCost: 12.94,
          todayCost: 0.08,
          dbExists: true,
          dailyCosts: [],
          recentTasks: [
            mockTask({
              status: "completed",
              query_text: "Index Q1 2026 meeting transcripts into memory",
              created_at: iso(47),
              completed_at: iso(45),
              cost_usd: 0.02,
            }),
            mockTask({
              status: "completed",
              query_text: "Consolidate project notes from April planning sync",
              created_at: iso(210),
              completed_at: iso(205),
              cost_usd: 0.03,
            }),
            mockTask({
              status: "failed",
              query_text: "Merge legacy archive shards — partition 04",
              created_at: iso(540),
              completed_at: iso(535),
              error_message: "Partition checksum mismatch",
            }),
          ],
        },
      },
      {
        bot: { id: "scribe", label: "Scribe", color: "#d98b57", colorRgb: "217, 139, 87" },
        stats: {
          botId: "scribe",
          totalTasks: 0,
          activeTasks: 0,
          completedTasks: 0,
          failedTasks: 0,
          queuedTasks: 0,
          totalQueries: 0,
          totalCost: 0,
          todayCost: 0,
          dbExists: false,
          dailyCosts: [],
          recentTasks: [],
        },
      },
    ];
  });

  const rosterEntries = visibleEntries.length > 0 ? visibleEntries : rosterMockEntries;

  const historyStrings = useMemo<ExecutionHistoryStrings>(
    () => ({
      empty: t("overview.history.empty"),
      noMessage: t("overview.history.noMessage"),
      status: {
        completed: t("overview.history.status.completed"),
        failed: t("overview.history.status.failed"),
        running: t("overview.history.status.running"),
        retrying: t("overview.history.status.retrying"),
        queued: t("overview.history.status.queued"),
      },
    }),
    [t],
  );

  const buildBotUrl = useCallback(
    (botId: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (botId) {
        params.set("bot", botId);
      } else {
        params.delete("bot");
      }

      const query = params.toString();
      return query ? `/?${query}` : "/";
    },
    [searchParams]
  );

  const closeBotModal = useCallback(() => {
    router.push(buildBotUrl(null), { scroll: false });
  }, [buildBotUrl, router]);

  const changeModalBot = useCallback(
    (botId: string) => {
      router.push(buildBotUrl(botId), { scroll: false });
    },
    [buildBotUrl, router]
  );

  const tourVariant =
    loading && !allStats ? "loading" : visibleEntries.length === 0 ? "empty" : "default";

  const [heatmapPeriod, setHeatmapPeriod] = useState<"all" | "30d" | "7d">("all");
  const dailyActivity = useDailyActivity(visibleEntries, { weeks: 26 });

  const statsWindowDays = heatmapPeriod === "7d" ? 7 : heatmapPeriod === "30d" ? 30 : dailyActivity.totalDays;

  const heatmapStats = useMemo(() => {
    const { cells } = dailyActivity;
    const windowCells = statsWindowDays >= cells.length ? cells : cells.slice(-statsWindowDays);

    let activeDays = 0;
    let totalSignals = 0;
    let peakCell = { date: "", count: 0 };
    let longestStreak = 0;
    let currentStreak = 0;

    for (const cell of windowCells) {
      totalSignals += cell.count;
      if (cell.count > 0) {
        activeDays += 1;
        currentStreak += 1;
        if (currentStreak > longestStreak) longestStreak = currentStreak;
        if (cell.count > peakCell.count) peakCell = { date: cell.date, count: cell.count };
      } else {
        currentStreak = 0;
      }
    }

    return {
      activeDays,
      totalSignals,
      peakCell,
      longestStreak,
    };
  }, [dailyActivity, statsWindowDays]);

  const heatmapPeriodTabs = useMemo(
    () => [
      { id: "all" as const, label: t("overview.heatmap.tabs.all") },
      { id: "30d" as const, label: t("overview.heatmap.tabs.30d") },
      { id: "7d" as const, label: t("overview.heatmap.tabs.7d") },
    ],
    [t],
  );

  const heatmapStatsDisplay = useMemo(() => {
    const formatPeakDate = (iso: string) => {
      const parts = iso.split("-");
      if (parts.length !== 3) return iso;
      return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])).toLocaleDateString(
        undefined,
        { month: "short", day: "numeric" },
      );
    };
    return [
      {
        label: t("overview.heatmap.stats.activeDays"),
        value: heatmapStats.activeDays.toLocaleString(),
      },
      {
        label: t("overview.heatmap.stats.totalSignals"),
        value: heatmapStats.totalSignals.toLocaleString(),
      },
      {
        label: t("overview.heatmap.stats.peakDay"),
        value:
          heatmapStats.peakCell.count > 0
            ? formatPeakDate(heatmapStats.peakCell.date)
            : "—",
        hint:
          heatmapStats.peakCell.count > 0
            ? t("overview.heatmap.stats.peakHint", { count: heatmapStats.peakCell.count })
            : undefined,
      },
      {
        label: t("overview.heatmap.stats.longestStreak"),
        value: t("overview.heatmap.stats.days", { count: heatmapStats.longestStreak }),
      },
    ];
  }, [heatmapStats, t]);


  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    let key: "morning" | "afternoon" | "evening" | "night" = "morning";
    if (hour >= 5 && hour < 12) key = "morning";
    else if (hour >= 12 && hour < 18) key = "afternoon";
    else if (hour >= 18 && hour < 23) key = "evening";
    else key = "night";
    return t(`overview.greeting.${key}`, { name: "Ryan" });
  }, [t]);

  const composerActions = useMemo(
    () => [
      {
        id: "run-task",
        label: t("overview.composer.actions.runTask"),
        icon: Play,
        onSelect: () => router.push("/runtime"),
      },
      {
        id: "new-schedule",
        label: t("overview.composer.actions.newSchedule"),
        icon: CalendarPlus,
        onSelect: () => router.push("/schedules"),
      },
      {
        id: "new-agent",
        label: t("overview.composer.actions.newAgent"),
        icon: Sparkles,
        onSelect: () => router.push("/control-plane"),
      },
      {
        id: "review-memory",
        label: t("overview.composer.actions.reviewMemory"),
        icon: BookOpen,
        onSelect: () => router.push("/memory"),
      },
    ],
    [t, router],
  );

  const heatmapTooltipTemplate = useCallback(
    (cell: { date: string; count: number }) => {
      const parts = cell.date.split("-");
      const formatted =
        parts.length === 3
          ? new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])).toLocaleDateString(
              undefined,
              { month: "short", day: "numeric", year: "numeric" },
            )
          : cell.date;
      if (cell.count <= 0) {
        return t("overview.heatmap.emptyTooltip", { date: formatted });
      }
      return t("overview.heatmap.tooltip", { count: cell.count, date: formatted });
    },
    [t],
  );

  if (loading && !allStats) {
    return (
      <div className="mx-auto flex w-full max-w-[900px] flex-col items-center gap-10 pt-12">
        <div className="h-10 w-full max-w-[420px] animate-pulse rounded-[var(--radius-input)] bg-[var(--panel-soft)]" />
        <div className="h-24 w-full animate-pulse rounded-[var(--radius-input)] bg-[var(--panel-soft)]" />
      </div>
    );
  }

  return (
    <>
      <div className="relative" {...tourRoute("overview", tourVariant)}>
        <section className="mx-auto flex w-full max-w-[760px] flex-col items-stretch gap-7 pt-10 pb-2">
          <header className="flex flex-col items-center gap-3 text-center">
            <h1 className="m-0 text-center font-medium text-[var(--text-primary)] [font-size:var(--font-size-display)] [letter-spacing:var(--tracking-display)]">
              {greeting}
            </h1>
          </header>

          <div {...tourAnchor("overview.composer")}>
            <OverviewComposer
              placeholder={t("overview.composer.placeholder")}
              submitLabel={t("overview.composer.submit")}
              actions={composerActions}
              onSubmit={() => router.push("/runtime")}
            />
          </div>
        </section>

        <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 pt-6">
          <div className="w-full" {...tourAnchor("overview.activity")}>
            <ActivityHeatmap
              data={dailyActivity}
              title={t("overview.heatmap.title")}
              subtitle={t("overview.heatmap.subtitle")}
              tooltipTemplate={heatmapTooltipTemplate}
              periods={heatmapPeriodTabs}
              periodValue={heatmapPeriod}
              onPeriodChange={(id) => setHeatmapPeriod(id as "all" | "30d" | "7d")}
              stats={heatmapStatsDisplay}
              legend={{ less: t("overview.heatmap.less"), more: t("overview.heatmap.more") }}
              scopeSlot={
                <div className="w-[200px]" {...tourAnchor("overview.bot-switcher")}>
                  <BotSwitcher
                    multiple
                    singleRow
                    selectedBotIds={selectedBotIds}
                    onSelectionChange={setSelectedBotIds}
                    className="bot-switcher--compact"
                  />
                </div>
              }
            />
          </div>

          <section className="w-full" {...tourAnchor("overview.history")}>
            <header className="mb-3 flex items-baseline justify-between px-3">
              <h3 className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
                {t("overview.history.title")}
              </h3>
              <span className="eyebrow">{t("overview.history.subtitle")}</span>
            </header>
            <ExecutionHistory
              entries={rosterEntries}
              strings={historyStrings}
              limit={10}
              onSelectBot={(botId) => router.push(buildBotUrl(botId), { scroll: false })}
            />
          </section>
        </div>

      </div>

      {modalBotId ? (
        <BotDetailModal
          botId={modalBotId}
          isOpen={Boolean(modalBotId)}
          onClose={closeBotModal}
          onBotChange={changeModalBot}
        />
      ) : null}
    </>
  );
}
