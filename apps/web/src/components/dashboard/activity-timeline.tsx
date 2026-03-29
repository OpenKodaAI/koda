"use client";

import { cn, formatRelativeTime } from "@/lib/utils";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import { getSemanticStyle, type SemanticTone } from "@/lib/theme-semantic";
import { useAppI18n } from "@/hooks/use-app-i18n";

function getActivityTone(type: string): SemanticTone {
  if (["completed", "task_completed"].includes(type)) {
    return "success";
  }

  if (["running", "task_started"].includes(type)) {
    return "info";
  }

  if (["queued", "task_queued", "cron"].includes(type)) {
    return "warning";
  }

  if (["failed", "task_failed", "error"].includes(type)) {
    return "danger";
  }

  if (["retrying", "retry"].includes(type)) {
    return "retry";
  }

  return "neutral";
}

interface Activity {
  botId: string;
  type: string;
  description: string;
  timestamp: string;
}

interface ActivityTimelineProps {
  activities: Activity[];
  className?: string;
}

const MAX_DISPLAYED = 8;

export function ActivityTimeline({
  activities,
  className,
}: ActivityTimelineProps) {
  const { t } = useAppI18n();
  const displayedActivities = activities.slice(0, MAX_DISPLAYED);
  const hasMore = activities.length > MAX_DISPLAYED;
  const typeLabels: Record<string, string> = {
    completed: t("runtime.labels.completed"),
    running: t("runtime.labels.running"),
    queued: t("runtime.labels.queued"),
    failed: t("runtime.labels.failed"),
    retrying: t("runtime.labels.retrying"),
    task_completed: t("overview.activity.taskCompleted", { defaultValue: "Task completed" }),
    task_failed: t("overview.activity.taskFailed", { defaultValue: "Task failed" }),
    task_started: t("overview.activity.taskStarted", { defaultValue: "Task started" }),
    task_queued: t("overview.activity.taskQueued", { defaultValue: "Task queued" }),
    query: t("common.query"),
    error: t("sessions.detail.error"),
    cron: t("routeMeta.schedules.title"),
    deploy: t("overview.activity.deploy", { defaultValue: "Deploy" }),
    retry: t("overview.activity.retry", { defaultValue: "Retry" }),
  };

  return (
    <section className={cn("glass-card flex h-full flex-col p-5 lg:p-6", className)}>
      <div className="mb-5 flex items-end justify-between gap-3 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <p className="eyebrow">{t("overview.sections.recentActivityTitle")}</p>
          <h3 className="mt-1.5 text-[1.08rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)] sm:text-[1.16rem]">
            {t("overview.activity.latestExecutions", { defaultValue: "Latest executions" })}
          </h3>
        </div>
        <span className="chip shrink-0">
          {t("overview.activity.events", { count: activities.length, defaultValue: "{{count}} events" })}
        </span>
      </div>

      {activities.length === 0 ? (
        <p className="py-8 text-center text-sm text-[var(--text-tertiary)]">
          {t("overview.activity.noRecent", { defaultValue: "No recent activity" })}
        </p>
      ) : (
        <>
          <ul className="space-y-0">
            {displayedActivities.map((activity, index) => (
              <li
                key={`${activity.timestamp}-${index}`}
                className="grid grid-cols-[16px_minmax(0,1fr)] gap-3.5"
              >
                <div className="relative flex justify-center">
                  <span
                    className="relative z-10 mt-1.5 block h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: getBotColor(activity.botId) }}
                  />
                  {index < displayedActivities.length - 1 && (
                    <div className="absolute top-[18px] bottom-[-14px] w-px bg-[var(--border-subtle)]" />
                  )}
                </div>

                <div
                  className={cn(
                    "min-w-0 pb-4",
                    index < displayedActivities.length - 1 && "border-b border-[var(--border-subtle)]"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]"
                          style={{
                            backgroundColor: `${getBotColor(activity.botId)}14`,
                            borderColor: `${getBotColor(activity.botId)}24`,
                          }}
                        >
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{ backgroundColor: getBotColor(activity.botId) }}
                          />
                          {getBotLabel(activity.botId)}
                        </span>
                        <span
                          className="inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]"
                          style={getSemanticStyle(getActivityTone(activity.type))}
                        >
                          {typeLabels[activity.type] ?? activity.type}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-[14px] leading-6 text-[var(--text-primary)]">
                        {activity.description}
                      </p>
                    </div>
                    <span className="shrink-0 pt-0.5 text-[11px] text-[var(--text-tertiary)]">
                      {formatRelativeTime(activity.timestamp)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {hasMore && (
            <p className="mt-4 text-center text-[11px] uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              {t("overview.activity.showingRecent", { defaultValue: "Showing the most recent events" })}
            </p>
          )}
        </>
      )}
    </section>
  );
}
