"use client";

import { useState, type ReactNode } from "react";
import {
  Activity,
  CheckCircle,
  Clock3,
  RefreshCcw,
  XCircle,
  Zap,
} from "lucide-react";
import { CronTable } from "@/components/schedules/cron-table";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { TaskDetail } from "@/components/tasks/task-detail";
import { TaskTable } from "@/components/tasks/task-table";
import { useAgentDetail } from "@/hooks/use-agent-detail";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { Task } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatRelativeTime,
} from "@/lib/utils";

type Tab = "overview" | "tasks" | "sessions" | "cron";

interface AgentDetailContentProps {
  agentId: string;
}

function AgentDetailSkeleton() {
  return (
    <div className="space-y-4">
      <div className="app-section p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <div className="space-y-3">
            <div className="skeleton skeleton-text w-28" />
            <div className="skeleton skeleton-heading w-64" />
            <div className="skeleton skeleton-text w-full" />
            <div className="grid grid-cols-2 gap-3 pt-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="app-kpi-card">
                  <div className="skeleton skeleton-text mb-2 w-16" />
                  <div className="skeleton skeleton-heading w-20" />
                </div>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="app-kpi-card">
                <div className="skeleton skeleton-text mb-2 w-16" />
                <div className="skeleton skeleton-heading w-24" />
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="app-section p-5 sm:p-6">
        <div className="skeleton skeleton-text w-32" />
        <div className="mt-4 grid gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton skeleton-text w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function AgentDetailContent({ agentId }: AgentDetailContentProps) {
  const { t } = useAppI18n();
  const { agentDisplayMap } = useAgentCatalog();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [selectedTask, setSelectedTask] = useState<(Task & { agentId?: string }) | null>(
    null
  );
  const { stats, tasks, sessions, cronJobs, loading, error, refresh } = useAgentDetail(agentId, activeTab);

  const agentDisplay = agentDisplayMap[agentId] ?? {
    id: agentId,
    label: agentId,
    color: "#D2D4D9",
    colorRgb: "210, 212, 217",
  };

  const lastActivity = stats?.recentTasks[0]?.created_at;
  const recentTasks = (stats?.recentTasks.length ? stats.recentTasks : tasks.slice(0, 8)).map(
    (task) => ({
      ...task,
      agentId,
    })
  );

  if (loading && !stats) {
    return <AgentDetailSkeleton />;
  }

  if (error && !stats) {
    return (
      <div className="app-section p-6">
        <p className="text-lg font-semibold text-[var(--text-primary)]">
          {t("agentDetail.unavailable")}
        </p>
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{error}</p>
      </div>
    );
  }

  if (stats && !stats.dbExists) {
    return (
      <div className="app-section p-6 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <h2 className="text-[1.7rem] font-semibold tracking-[-0.055em] text-[var(--text-primary)]">
              {t("agentDetail.databaseNotInitialized")}
            </h2>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3 text-sm text-[var(--text-secondary)]">
            {t("agentDetail.noPublishedData")}
          </div>
        </div>
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  return (
    <>
      <div className="space-y-4">
        <section className="app-section p-5 sm:p-6 lg:p-7">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] xl:items-start">
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: agentDisplay.color }}
                />
                <StatusIndicator
                  status={stats.activeTasks > 0 ? "running" : "completed"}
                  showLabel
                />
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="button-shell button-shell--secondary button-shell--sm gap-2 px-3 text-[var(--text-secondary)]"
                >
                  <RefreshCcw className="h-3.5 w-3.5" />
                  {t("agentDetail.refresh")}
                </button>
              </div>

              <div>
                <h2 className="text-[1.55rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)] sm:text-[1.75rem]">
                  {stats.activeTasks > 0
                    ? t("agentDetail.activeTitle", { agent: agentDisplay.label })
                    : t("agentDetail.stableTitle", { agent: agentDisplay.label })}
                </h2>
              </div>

              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <HeroMetric icon={<Zap className="h-4 w-4" />} label={t("agentDetail.metrics.active")} value={stats.activeTasks} />
                <HeroMetric
                  icon={<CheckCircle className="h-4 w-4" />}
                  label={t("agentDetail.metrics.completed")}
                  value={stats.completedTasks}
                />
                <HeroMetric icon={<XCircle className="h-4 w-4" />} label={t("agentDetail.metrics.failed")} value={stats.failedTasks} />
                <HeroMetric icon={<Activity className="h-4 w-4" />} label={t("agentDetail.metrics.queries")} value={stats.totalQueries} />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <SummaryMetric label={t("agentDetail.metrics.todayCost")} value={formatCost(stats.todayCost)} />
              <SummaryMetric label={t("agentDetail.metrics.totalCost")} value={formatCost(stats.totalCost)} />
              <SummaryMetric
                label={t("agentDetail.metrics.lastActivity")}
                value={lastActivity ? formatRelativeTime(lastActivity) : t("common.noHistory")}
              />
              <SummaryMetric label={t("agentDetail.metrics.schedules")} value={`${cronJobs.length}`} />
            </div>
          </div>
        </section>

        <div className="segmented-control segmented-control--full bg-[var(--surface-elevated-soft)]">
          {[
            { key: "overview", label: t("agentDetail.tabs.overview") },
            { key: "tasks", label: t("agentDetail.tabs.tasks") },
            { key: "sessions", label: t("agentDetail.tabs.sessions") },
            { key: "cron", label: t("agentDetail.tabs.cron") },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key as Tab)}
              className={cn(
                "segmented-control__option",
                activeTab === tab.key && "is-active"
              )}
              style={
                activeTab === tab.key
                  ? {
                      background: `linear-gradient(180deg, ${agentDisplay.color}D6 0%, ${agentDisplay.color}92 100%)`,
                      borderColor: `${agentDisplay.color}38`,
                      color: "var(--text-primary)",
                      boxShadow: `inset 2px 2px 8px rgba(255,255,255,0.14), inset -2px -2px 7px rgba(0,0,0,0.14), 0 10px 18px ${agentDisplay.color}18`,
                    }
                  : undefined
              }
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "overview" && (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.42fr)_minmax(300px,0.78fr)]">
            <div className="app-section overflow-hidden">
              <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
                <h3 className="app-section__title">{t("agentDetail.recent")}</h3>
                <span className="chip">{t("agentDetail.entriesCount", { count: recentTasks.length })}</span>
              </div>
              {recentTasks.length === 0 ? (
                <EmptyBlock title={t("agentDetail.noRecentTasks")} />
              ) : (
                <TaskTable
                  tasks={recentTasks}
                  onTaskClick={setSelectedTask}
                  selectedTaskId={selectedTask?.id ?? null}
                />
              )}
            </div>

            <div className="space-y-4">
              <div className="app-section p-5">
                <div className="mt-4 space-y-3">
                  <StateRow
                    label={t("agentDetail.situation")}
                    value={
                      <StatusIndicator
                        status={stats.activeTasks > 0 ? "running" : "completed"}
                        showLabel
                      />
                    }
                  />
                  <StateRow
                    label={t("agentDetail.metrics.lastActivity")}
                    value={lastActivity ? formatRelativeTime(lastActivity) : t("common.noHistory")}
                  />
                  <StateRow label={t("agentDetail.activeSchedules")} value={cronJobs.length} />
                  <StateRow label={t("agentDetail.trackedSessions")} value={sessions.length} />
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "tasks" && (
          <div className="app-section overflow-hidden">
            <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
              <h3 className="app-section__title">{t("common.executions")}</h3>
              <span className="chip">{t("agentDetail.entriesCount", { count: tasks.length })}</span>
            </div>
            {tasks.length === 0 ? (
              <EmptyBlock title={t("agentDetail.noTask")} />
            ) : (
              <TaskTable
                tasks={tasks.map((task) => ({ ...task, agentId }))}
                onTaskClick={setSelectedTask}
                selectedTaskId={selectedTask?.id ?? null}
              />
            )}
          </div>
        )}

        {activeTab === "sessions" && (
          <div className="app-section overflow-hidden">
            <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
              <h3 className="app-section__title">{t("common.sessions")}</h3>
              <span className="chip">{sessions.length}</span>
            </div>
            {sessions.length === 0 ? (
              <EmptyBlock title={t("agentDetail.noSession")} />
            ) : (
              <div className="table-shell overflow-x-auto">
                <table className="glass-table min-w-full">
                  <thead>
                    <tr>
                      <th>{t("common.session")}</th>
                      <th>{t("common.summary")}</th>
                      <th>{t("agentDetail.metrics.queries")}</th>
                      <th>{t("common.created")}</th>
                      <th>{t("agentDetail.metrics.lastActivity")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((session) => (
                      <tr key={session.session_id}>
                        <td className="font-mono text-xs text-[var(--text-secondary)]">
                          {session.session_id?.slice(0, 16)}...
                        </td>
                        <td>{session.name || "—"}</td>
                        <td>{session.query_count}</td>
                        <td>{formatDateTime(session.created_at)}</td>
                        <td>{formatRelativeTime(session.last_used)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === "cron" && (
          <div className="app-section overflow-hidden">
            <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
              <h3 className="app-section__title">{t("common.schedules")}</h3>
              <span className="chip">{cronJobs.length}</span>
            </div>
            {cronJobs.length === 0 ? (
              <div className="p-5">
                <EmptyBlock title={t("agentDetail.noSchedule")} />
              </div>
            ) : (
              <div className="p-5">
                <CronTable
                  jobs={cronJobs}
                  agentLabel={agentDisplay.label}
                  agentColor={agentDisplay.color}
                />
              </div>
            )}
          </div>
        )}
      </div>

      <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />
    </>
  );
}

function HeroMetric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="app-kpi-card">
      <div className="flex items-center gap-2 text-[var(--text-secondary)]">
        {icon}
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </p>
      </div>
      <p className="mt-2 text-[1.45rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function SummaryMetric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="app-kpi-card">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function StateRow({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <span className="text-sm text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

function EmptyBlock({
  title,
}: {
  title: string;
}) {
  return (
    <div className="empty-state">
      <Clock3 className="empty-state-icon h-10 w-10" />
      <p className="empty-state-text">{title}</p>
    </div>
  );
}
