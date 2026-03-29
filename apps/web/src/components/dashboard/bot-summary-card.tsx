"use client";

import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";
import { getSemanticTextStyle, type SemanticTone } from "@/lib/theme-semantic";
import type { BotStats, Task } from "@/lib/types";

interface BotConfig {
  id: string;
  label: string;
  color: string;
  colorRgb: string;
}

interface BotSummaryCardProps {
  stats: BotStats;
  botConfig: BotConfig;
  className?: string;
  onClick?: () => void;
  active?: boolean;
}

const LIVE_STATUSES: Task["status"][] = ["running", "retrying", "queued"];

function getFeaturedTask(stats: BotStats) {
  return (
    stats.recentTasks.find((task) => LIVE_STATUSES.includes(task.status)) ??
    stats.recentTasks[0] ??
    null
  );
}

function getStatusMeta(
  stats: BotStats,
  featuredTask: Task | null,
  t: (key: string, options?: Record<string, unknown>) => string
) {
  if (!stats.dbExists) {
    return {
      label: t("overview.activity.noBase", { defaultValue: "No database" }),
      tone: "warning" as SemanticTone,
      pulse: false,
    };
  }

  if ((featuredTask && LIVE_STATUSES.includes(featuredTask.status)) || stats.activeTasks > 0) {
    return {
      label: t("overview.activity.executing", { defaultValue: "Running" }),
      tone: "info" as SemanticTone,
      pulse: true,
    };
  }

  return {
    label: featuredTask?.created_at
      ? t("overview.activity.lastDelivery", {
          defaultValue: "Last delivery",
        }) + " " + formatRelativeTime(featuredTask.created_at)
      : t("overview.activity.waitingForNewExecutions", {
          defaultValue: "Waiting for new executions",
        }),
    tone: "neutral" as SemanticTone,
    pulse: false,
  };
}

export function BotSummaryCard({
  stats,
  botConfig,
  className,
  onClick,
  active = false,
}: BotSummaryCardProps) {
  const { t, tl } = useAppI18n();
  const featuredTask = getFeaturedTask(stats);
  const status = getStatusMeta(stats, featuredTask, t);
  const taskText = !stats.dbExists
    ? t("overview.activity.waitingFirstExecution", {
        defaultValue: "Waiting for the first execution",
      })
    : featuredTask?.query_text?.trim() ||
      t("overview.activity.noPublishedMessage", {
        defaultValue: "No published message",
      });

  const content = (
    <div className="relative flex w-full items-start gap-3 py-3">
      <div className="shrink-0 self-start pt-0.5">
        <BotAgentGlyph
          botId={botConfig.id}
          color={botConfig.color}
          active={status.pulse}
          variant="list"
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex min-w-0 items-center gap-3">
          <p className="line-clamp-1 max-w-sm text-sm font-semibold text-[var(--text-primary)]">
            {botConfig.label}
          </p>
          <span
            className={cn(
              "ml-auto shrink-0 text-[11px] font-medium",
              status.pulse && "status-running"
            )}
            style={getSemanticTextStyle(status.tone, !status.pulse)}
          >
            {status.pulse
              ? t("runtime.overview.live", { defaultValue: "Live" })
              : featuredTask?.created_at
                ? formatRelativeTime(featuredTask.created_at)
                : "—"}
          </span>
        </div>

        <p className="line-clamp-1 max-w-2xl text-sm font-normal text-[var(--text-secondary)]">
          {truncateText(taskText, 140)}
        </p>
      </div>
    </div>
  );

  const classes = cn(
    "group relative w-full rounded-lg border border-transparent bg-transparent px-3 text-left transition-colors duration-75 hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] focus:outline-none focus-visible:ring-[1.5px] focus-visible:ring-inset focus-visible:ring-[var(--text-primary)]",
    active && "border-[var(--border-subtle)] bg-[var(--surface-hover)]",
    className
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={classes}
        aria-label={`${tl("Open bot summary")} ${botConfig.label}`}
      >
        {content}
      </button>
    );
  }

  return <article className={classes}>{content}</article>;
}
