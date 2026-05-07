"use client";


import { Suspense, useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  CalendarPlus,
  Play,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { ActivityHeatmap } from "@/components/dashboard/activity-heatmap";
import { SetupChecklistCard } from "@/components/dashboard/setup-checklist-card";
import { CommandBar } from "@/components/command-bar/command-bar";
import type { CommandBarContext } from "@/components/command-bar/command-registry";
import {
  ExecutionHistory,
  type ExecutionHistoryStrings,
} from "@/components/dashboard/execution-history";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { OverviewRouteLoading } from "@/components/layout/route-loading";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useOptionalAuth, type AuthOperator } from "@/components/providers/auth-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useDailyActivity } from "@/hooks/use-daily-activity";
import { useSetupChecklist } from "@/hooks/use-setup-checklist";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAgentStats } from "@/hooks/use-agent-stats";
import { resolveAgentSelection } from "@/lib/agent-selection";
import { cn } from "@/lib/utils";
import type { AgentStats } from "@/lib/types";

function deriveGreetingName(operator: AuthOperator | null | undefined): string {
  const candidate =
    operator?.display_name?.trim() ||
    operator?.username?.trim() ||
    "";
  if (!candidate || candidate.includes("@") || candidate.includes(".")) {
    return "Operator";
  }
  return candidate.split(/\s+/)[0] || "Operator";
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<OverviewPageFallback />}>
      <OverviewPageContent />
    </Suspense>
  );
}

function OverviewPageFallback() {
  return <OverviewRouteLoading />;
}

function OverviewPageContent() {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const auth = useOptionalAuth();
  const router = useRouter();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const {
    stats: allStats,
    loading,
  } = useAgentStats();
  const { snapshot: setupChecklistSnapshot } = useSetupChecklist();

  const openAgentDetail = useCallback(
    (agentId: string) => {
      router.push(`/control-plane/agents/${encodeURIComponent(agentId)}`);
    },
    [router]
  );

  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );

  const statsByAgent = useMemo(
    () => {
      const statsMap = Object.fromEntries(
        (allStats ?? []).map((stats) => [stats.agentId, stats]),
      ) as Record<string, AgentStats>;
      return agents.map((agent) => ({
        agent,
        stats: statsMap[agent.id],
      }));
    },
    [allStats, agents],
  );

  const visibleEntries = useMemo(
    () =>
      statsByAgent.filter((entry) => visibleBotIds.includes(entry.agent.id)),
    [statsByAgent, visibleBotIds]
  );

  const rosterEntries = visibleEntries;

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
    return t(`overview.greeting.${key}`, { name: deriveGreetingName(auth?.operator) });
  }, [auth?.operator, t]);

  const quickPills = useMemo<Array<{ id: string; label: string; icon: LucideIcon; onSelect: () => void }>>(
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
        onSelect: () => router.push("/routines/schedules"),
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

  const commandBarCtx = useMemo<CommandBarContext>(
    () => ({
      agents,
      stats: allStats,
      router: { push: (href: string) => router.push(href) },
      t,
      openAgentDetail,
    }),
    [allStats, agents, openAgentDetail, router, t],
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
    return <OverviewRouteLoading />;
  }

  return (
    <>
      <div className="relative" {...tourRoute("overview", tourVariant)}>
        <section className="mx-auto flex w-full max-w-[760px] flex-col items-stretch gap-7 pt-10 pb-2">
          <header className="flex flex-col items-center gap-3 text-center">
            <h1 className="display-serif m-0 text-center font-medium text-[var(--text-primary)] [font-size:var(--font-size-display)]">
              {greeting}
            </h1>
          </header>

          <div {...tourAnchor("overview.composer")}>
            <CommandBar
              ctx={commandBarCtx}
              mode="inline"
              placeholder={t("commandBar.placeholder")}
              emptyState={t("commandBar.emptyState")}
              shortcutHint={t("commandBar.shortcutHint")}
              pillsSlot={
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {quickPills.map((pill) => {
                    const Icon = pill.icon;
                    return (
                      <button
                        key={pill.id}
                        type="button"
                        onClick={pill.onSelect}
                        className={cn(
                          "inline-flex h-8 items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-transparent px-3 text-[0.8125rem] font-medium text-[var(--text-secondary)]",
                          "transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
                        )}
                      >
                        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>{pill.label}</span>
                      </button>
                    );
                  })}
                </div>
              }
            />
          </div>
        </section>

        <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 pt-6">
          <SetupChecklistCard snapshot={setupChecklistSnapshot} />
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
                <div className="w-[200px]" {...tourAnchor("overview.agent-switcher")}>
                  <AgentSwitcher
                    multiple
                    singleRow
                    selectedBotIds={selectedBotIds}
                    onSelectionChange={setSelectedBotIds}
                    className="agent-switcher--compact"
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
              onSelectAgent={openAgentDetail}
            />
          </section>
        </div>

      </div>

    </>
  );
}
