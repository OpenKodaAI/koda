"use client";


import dynamic from "next/dynamic";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { RuntimeControlCard } from "@/components/dashboard/runtime-control-card";
import { StatsGrid } from "@/components/dashboard/stats-grid";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import type {
  AgentPlanMetadataItem,
  AgentPlanStatus,
  AgentPlanTask,
} from "@/components/ui/agent-plan";
import { useBotStats } from "@/hooks/use-bot-stats";
import {
  formatBotSelectionLabel,
  resolveBotSelection,
} from "@/lib/bot-selection";
import { getBotChartColor } from "@/lib/bot-constants";
import { translate } from "@/lib/i18n";
import { formatCost, formatRelativeTime, truncateText } from "@/lib/utils";
import type { BotStats, Task } from "@/lib/types";

const BotDetailModal = dynamic(
  () =>
    import("@/components/bots/bot-detail-modal").then((module) => ({
      default: module.BotDetailModal,
    })),
  { loading: () => null },
);

const AgentPlan = dynamic(
  () => import("@/components/ui/agent-plan"),
  {
    loading: () => <div className="glass-card min-h-[220px] p-6" />,
  },
);

const ScreenTimeCard = dynamic(
  () =>
    import("@/components/ui/screen-time-card").then((module) => ({
      default: module.ScreenTimeCard,
    })),
  {
    loading: () => <div className="glass-card min-h-[220px] p-6" />,
  },
);

const LIVE_TASK_STATUSES: Task["status"][] = ["queued", "running", "retrying"];

function parseTaskDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function estimateTaskDurationMs(task: Task) {
  const startDate =
    parseTaskDate(task.started_at) ??
    parseTaskDate(task.created_at) ??
    parseTaskDate(task.completed_at);

  if (!startDate) return 0;

  const endDate = parseTaskDate(task.completed_at);

  if (!endDate) return 0;

  return Math.min(Math.max(endDate.getTime() - startDate.getTime(), 0), 4 * 60 * 60 * 1000);
}

function getPlanStatusFromTask(task: Task | null | undefined): AgentPlanStatus {
  if (!task) return "pending";

  if (task.status === "failed") return "failed";
  if (LIVE_TASK_STATUSES.includes(task.status)) return "in-progress";
  if (task.status === "completed") return "completed";
  return "pending";
}

function getPlanStatusFromBot(stats: BotStats, featuredTask: Task | null): AgentPlanStatus {
  if (!stats.dbExists) return "pending";
  if (stats.activeTasks > 0 || (featuredTask && LIVE_TASK_STATUSES.includes(featuredTask.status))) {
    return "in-progress";
  }
  if (featuredTask?.status === "failed") return "failed";
  if (featuredTask?.status === "completed") return "completed";
  return "pending";
}

function getTaskStatusCopy(task: Task) {
  switch (task.status) {
    case "running":
      return translate("overview.taskStatus.running");
    case "retrying":
      return translate("overview.taskStatus.retrying");
    case "queued":
      return translate("overview.taskStatus.queued");
    case "completed":
      return translate("overview.taskStatus.completed");
    case "failed":
      return translate("overview.taskStatus.failed");
    default:
      return task.status;
  }
}

function getTaskStatusTone(task: Task): AgentPlanMetadataItem["tone"] {
  switch (task.status) {
    case "running":
    case "retrying":
      return "info";
    case "queued":
      return "warning";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

function buildExecutionMetadata(task: Task | null | undefined): AgentPlanMetadataItem[] {
  if (!task) return [];

  const items: Array<AgentPlanMetadataItem | null> = [
    {
      id: "status",
      label: "estado",
      value: getTaskStatusCopy(task),
      tone: getTaskStatusTone(task),
      live: LIVE_TASK_STATUSES.includes(task.status),
    },
    task.session_id
      ? {
          id: "session",
          label: translate("common.session", { defaultValue: "session" }),
          value: task.session_id.slice(0, 8),
          tone: "neutral",
        }
      : null,
    task.model
      ? {
          id: "model",
          label: "modelo",
          value: truncateText(task.model, 18),
          tone: "neutral",
        }
      : null,
    {
      id: "attempt",
      label: translate("overview.activity.attemptLabel", { defaultValue: "attempt" }),
      value: `${task.attempt}/${task.max_attempts}`,
      tone: task.attempt > 1 ? "warning" : "neutral",
    },
    task.cost_usd > 0 || task.status === "completed" || task.status === "failed"
      ? {
          id: "cost",
          label: "custo",
          value: formatCost(task.cost_usd),
          tone: task.cost_usd > 0 ? "info" : "neutral",
        }
      : null,
  ];

  return items.filter((item): item is AgentPlanMetadataItem => Boolean(item));
}

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
  } = useBotStats(undefined, 2000);

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

  const totalTasks = visibleEntries.reduce(
    (sum, entry) => sum + (entry.stats?.totalTasks ?? 0),
    0
  );
  const totalActive = visibleEntries.reduce(
    (sum, entry) => sum + (entry.stats?.activeTasks ?? 0),
    0
  );
  const totalQueries = visibleEntries.reduce(
    (sum, entry) => sum + (entry.stats?.totalQueries ?? 0),
    0
  );
  const totalCostToday = visibleEntries.reduce(
    (sum, entry) => sum + (entry.stats?.todayCost ?? 0),
    0
  );
  const totalPeriodCost = visibleEntries.reduce(
    (sum, entry) =>
      sum + (entry.stats?.dailyCosts ?? []).reduce((seriesSum, item) => seriesSum + item.cost, 0),
    0
  );

  const activeBots = visibleEntries.filter((entry) => entry.stats?.dbExists);
  const waitingBots = visibleEntries.filter((entry) => !entry.stats?.dbExists);
  const scopeLabel = formatBotSelectionLabel(visibleBotIds, bots);

  const activityMonitor = useMemo(() => {
    const hourlyActivity = Array.from({ length: 24 }, () => 0);
    let totalDurationMs = 0;

    const topApps = visibleEntries
      .map((entry) => {
        const recentTasks = entry.stats?.recentTasks ?? [];
        const featuredTask =
          recentTasks.find((task) => LIVE_TASK_STATUSES.includes(task.status)) ??
          recentTasks[0] ??
          null;

        let activityScore = (entry.stats?.activeTasks ?? 0) * 12;
        let botDurationMs = 0;

        recentTasks.forEach((task) => {
          const date =
            parseTaskDate(task.started_at) ??
            parseTaskDate(task.created_at) ??
            parseTaskDate(task.completed_at);

          if (date) {
            hourlyActivity[date.getHours()] += LIVE_TASK_STATUSES.includes(task.status) ? 1.6 : 1;
          }

          const durationMs = estimateTaskDurationMs(task);
          totalDurationMs += durationMs;
          botDurationMs += durationMs;
          activityScore += LIVE_TASK_STATUSES.includes(task.status) ? 6 : 2;
        });

        const statusLabel = entry.stats?.activeTasks
          ? t("overview.activity.activeNow", { count: entry.stats.activeTasks })
          : featuredTask?.created_at
            ? t("overview.activity.lastActivity", { value: formatRelativeTime(featuredTask.created_at) })
            : entry.stats?.dbExists
              ? t("overview.activity.waiting")
              : t("overview.activity.noBase");

        return {
          name: entry.bot.label,
          duration: statusLabel,
          score: activityScore + botDurationMs / 60000,
          color: getBotChartColor(entry.bot.id),
          icon: (
            <BotAgentGlyph
              botId={entry.bot.id}
              color={entry.bot.color}
              active={(entry.stats?.activeTasks ?? 0) > 0}
              variant="list"
              className="h-5 w-5"
            />
          ),
        };
      })
      .sort((left, right) => right.score - left.score)
      .slice(0, 4);

    const totalMinutes = Math.round(totalDurationMs / 60000);

    return {
      totalHours: Math.floor(totalMinutes / 60),
      totalMinutes: totalMinutes % 60,
      barData: hourlyActivity,
      topApps:
        topApps.length > 0
          ? topApps
          : [
              {
                icon: <Activity className="h-4 w-4" />,
                name: t("overview.activity.noPublishedActivity"),
                duration: t("overview.activity.waitingForNewExecutions"),
              },
            ],
    };
  }, [t, visibleEntries]);

  const agentPlanTasks = useMemo<AgentPlanTask[]>(
    () =>
      visibleEntries.flatMap((entry) => {
        if (!entry.stats) return [];

        const recentTasks = entry.stats.recentTasks ?? [];
        const featuredTask =
          recentTasks.find((task) => LIVE_TASK_STATUSES.includes(task.status)) ??
          recentTasks[0] ??
          null;

        const dependencies: string[] = [];
        if (entry.stats.activeTasks > 0) {
          dependencies.push(t("overview.activity.activeTasksCount", { count: entry.stats.activeTasks }));
        } else if (featuredTask?.created_at) {
          dependencies.push(formatRelativeTime(featuredTask.created_at));
        }
        if (entry.stats.totalQueries > 0) {
          dependencies.push(t("overview.activity.queriesCount", { count: entry.stats.totalQueries }));
        }

        const subtasks: AgentPlanTask["subtasks"] =
          recentTasks.length > 0
            ? recentTasks.slice(0, 5).map((task) => ({
                id: `${entry.bot.id}-${task.id}`,
                title: truncateText(task.query_text?.trim() || t("overview.activity.noPublishedMessage"), 96),
                description: [
                  task.status === "completed"
                    ? t("overview.activity.completed", { value: formatRelativeTime(task.created_at) })
                    : task.status === "failed"
                      ? t("overview.activity.failed", { value: formatRelativeTime(task.created_at) })
                      : t("overview.activity.activeAt", { value: formatRelativeTime(task.created_at) }),
                  task.model ?? null,
                  task.cost_usd > 0 ? formatCost(task.cost_usd) : null,
                ]
                  .filter(Boolean)
                  .join(" • "),
                status: getPlanStatusFromTask(task),
                priority: LIVE_TASK_STATUSES.includes(task.status) ? "high" : "medium",
                metadata: buildExecutionMetadata(task),
                liveSince: LIVE_TASK_STATUSES.includes(task.status)
                  ? task.started_at ?? task.created_at
                  : null,
                tags: [
                  `status ${task.status}`,
                  task.session_id ? t("overview.activity.session", { value: task.session_id.slice(0, 8) }) : null,
                  t("overview.activity.attempt", { current: task.attempt, max: task.max_attempts }),
                ].filter((value): value is string => Boolean(value)),
              }))
            : [
                {
                  id: `${entry.bot.id}-empty`,
                  title: entry.stats.dbExists
                    ? t("overview.activity.noRecentExecution", { defaultValue: "No recent execution" })
                    : t("overview.activity.waitingFirstExecution"),
                  description: entry.stats.dbExists
                    ? t("overview.activity.connectedNoRecent")
                    : t("overview.activity.botNotReady"),
                  status: entry.stats.dbExists ? "pending" : "need-help",
                  priority: "low",
                  metadata: [
                    {
                      id: "base",
                      label: t("overview.activity.base"),
                      value: entry.stats.dbExists ? t("overview.activity.connected") : t("overview.activity.pending"),
                      tone: entry.stats.dbExists ? "neutral" : "warning",
                    },
                    {
                      id: "queries",
                      label: t("overview.activity.queries"),
                      value: String(entry.stats.totalQueries),
                      tone: "neutral",
                    },
                  ],
                  tags: [
                    entry.stats.dbExists ? t("overview.activity.baseConnected", { defaultValue: "connected base" }) : t("overview.activity.noBaseTag", { defaultValue: "no base" }),
                    t("overview.activity.queriesCount", { count: entry.stats.totalQueries, defaultValue: "{{count}} queries" }),
                  ],
                },
              ];

        return [
          {
            id: entry.bot.id,
            title: entry.bot.label,
            description: !entry.stats.dbExists
              ? t("overview.activity.waitingFirstPublishedExecution", { defaultValue: "Waiting for the first published execution to start the live plan." })
              : featuredTask?.query_text
                ? `${
                    LIVE_TASK_STATUSES.includes(featuredTask.status)
                      ? t("overview.activity.executing")
                      : t("overview.activity.lastDelivery")
                  }: ${truncateText(featuredTask.query_text, 140)}`
                : t("overview.activity.noRecentPublished", { defaultValue: "No recent activity published in the current selection." }),
            status: getPlanStatusFromBot(entry.stats, featuredTask),
            priority: entry.stats.activeTasks > 0 ? "high" : "medium",
            level: 0,
            dependencies,
            metadata: featuredTask
              ? buildExecutionMetadata(featuredTask)
              : [
                  {
                    id: "base",
                    label: t("overview.activity.base"),
                    value: entry.stats.dbExists ? t("overview.activity.connected") : t("overview.activity.pending"),
                    tone: entry.stats.dbExists ? "neutral" : "warning",
                  },
                  {
                    id: "queries",
                    label: t("overview.activity.queries"),
                    value: String(entry.stats.totalQueries),
                    tone: "neutral",
                  },
                ],
            liveSince:
              featuredTask && LIVE_TASK_STATUSES.includes(featuredTask.status)
                ? featuredTask.started_at ?? featuredTask.created_at
                : null,
            subtasks,
          },
        ];
      }),
    [t, visibleEntries]
  );

  // globalStats removed — replaced by compactStats in render

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

  // Build sparkline from dailyCosts (the only complete time series available)
  // NOTE: Must be before early return to respect Rules of Hooks
  const costSparkline = useMemo(() => {
    const allDailyCosts = visibleEntries.flatMap(
      (entry) => entry.stats?.dailyCosts ?? [],
    );
    const byDate = new Map<string, number>();
    for (const item of allDailyCosts) {
      byDate.set(item.date, (byDate.get(item.date) ?? 0) + item.cost);
    }
    return Array.from(byDate.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-7)
      .map(([, cost]) => cost);
  }, [visibleEntries]);
  const tourVariant =
    loading && !allStats ? "loading" : visibleEntries.length === 0 ? "empty" : "default";

  if (loading && !allStats) {
    return (
      <div className="space-y-4">
        <div className="max-w-[350px]">
          <BotSwitcher multiple selectedBotIds={selectedBotIds} onSelectionChange={setSelectedBotIds} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="glass-card-sm p-5">
              <div className="skeleton skeleton-text mb-3" style={{ width: "40%" }} />
              <div className="skeleton skeleton-heading mb-2" style={{ width: "50%" }} />
              <div className="skeleton skeleton-text" style={{ width: "65%" }} />
            </div>
          ))}
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="app-section min-h-[340px] p-5 sm:p-6" />
          <div className="app-section min-h-[340px] p-5 sm:p-6" />
        </div>
        <div className="app-section min-h-[220px] p-5 sm:p-6 lg:p-7" />
      </div>
    );
  }

  const compactStats = [
    {
      label: t("overview.stats.totalTasks"),
      value: totalTasks,
      trend: scopeLabel,
      sparklineData: costSparkline,
      sparklineColor: "rgba(120,166,255,0.7)",
    },
    {
      label: t("overview.stats.activeTasks"),
      value: totalActive,
      trend: activeBots.length > 0 ? t("overview.stats.operating", { count: activeBots.length }) : t("overview.stats.noActiveOperation"),
      sparklineData: costSparkline,
      sparklineColor: "rgba(119,197,144,0.7)",
    },
    {
      label: t("overview.stats.totalQueries"),
      value: totalQueries,
      trend: waitingBots.length > 0 ? t("overview.stats.waiting", { count: waitingBots.length }) : t("overview.stats.coveragePublished"),
      sparklineData: costSparkline,
      sparklineColor: "rgba(168,140,210,0.7)",
    },
    {
      label: t("overview.stats.costToday"),
      value: formatCost(totalCostToday),
      trend: t("overview.stats.inPeriod", { value: formatCost(totalPeriodCost) }),
      sparklineData: costSparkline,
      sparklineColor: "rgba(228,180,84,0.7)",
    },
  ];

  return (
    <>
      <div className="space-y-4" {...tourRoute("overview", tourVariant)}>
        {/* Header: Bot selector */}
        <div className="max-w-[350px]" {...tourAnchor("overview.bot-switcher")}>
          <BotSwitcher
            multiple
            selectedBotIds={selectedBotIds}
            onSelectionChange={setSelectedBotIds}
          />
        </div>

        {/* Section 1: Compact metrics strip */}
        <div className="animate-in" {...tourAnchor("overview.stats")}>
          <StatsGrid stats={compactStats} />
        </div>

        {/* Section 2: Activity + Cost charts */}
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="app-section p-5 sm:p-6" {...tourAnchor("overview.activity")}>
            <div className="mb-4">
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("overview.sections.recentActivityTitle")}
              </h3>
            </div>
            <ScreenTimeCard
              totalHours={activityMonitor.totalHours}
              totalMinutes={activityMonitor.totalMinutes}
              barData={activityMonitor.barData}
              timeLabels={["00h", "06h", "12h", "18h", "23h"]}
              topApps={[]}
            />
          </section>

          <div {...tourAnchor("overview.runtime-control")}>
            <RuntimeControlCard selectedBotIds={selectedBotIds} />
          </div>
        </div>

        {/* Section 3: Live Plan */}
        <section className="app-section p-5 sm:p-6 lg:p-7" {...tourAnchor("overview.live-plan")}>
          <div className="app-section__header mb-5 border-b border-[var(--border-subtle)] pb-4">
            <div>
              <h3 className="app-section__title">{t("overview.sections.livePlanTitle")}</h3>
              <p className="app-section__description">
                {t("overview.sections.livePlanDescription")}
              </p>
            </div>
          </div>

          <AgentPlan
            tasks={agentPlanTasks}
            className="border-0 bg-transparent px-0 py-0 shadow-none"
          />
        </section>
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
