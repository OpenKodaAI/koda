"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatCost, formatDateTime, formatDuration, formatRelativeTime, truncateText } from "@/lib/utils";
import type { Task } from "@/lib/types";
import { getAgentColor } from "@/lib/agent-constants";
import { getSemanticTextStyle, type SemanticTone } from "@/lib/theme-semantic";
import { ListTodo, ArrowUpRight } from "lucide-react";
import { StatusPill } from "./status-pill";

interface TaskTableProps {
  tasks: (Task & { agentId?: string })[];
  showAgent?: boolean;
  loading?: boolean;
  onTaskClick?: (task: Task & { agentId?: string }) => void;
  selectedTaskId?: number | null;
}

function computeDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return "\u2014";
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const ms = end - start;
  if (ms < 0) return "\u2014";
  return formatDuration(ms);
}

function getDurationTone(startedAt: string | null, completedAt: string | null): SemanticTone {
  if (!startedAt || !completedAt) return "neutral";
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const ms = end - start;
  if (ms < 0) return "neutral";
  if (ms < 30000) return "success";
  if (ms <= 300000) return "warning";
  return "neutral";
}

const SKELETON_WIDTHS = ["60%", "45%", "75%", "50%", "40%", "55%", "35%", "30%"];

function formatSession(sessionId: string | null): string | null {
  if (!sessionId) return null;
  return sessionId.length > 14 ? `${sessionId.slice(0, 12)}…` : sessionId;
}

function SkeletonRow({ cols }: { cols: number }) {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i}>
          <div className="skeleton skeleton-text" style={{ width: SKELETON_WIDTHS[i % SKELETON_WIDTHS.length] }} />
        </td>
      ))}
    </tr>
  );
}

export function TaskTable({
  tasks,
  showAgent = false,
  loading = false,
  onTaskClick,
  selectedTaskId,
}: TaskTableProps) {
  const { t } = useAppI18n();
  const colCount = showAgent ? 8 : 7;

  return (
    <>
      <div className="hidden md:block">
        <div className="table-shell overflow-x-auto">
          <table className="glass-table min-w-[1040px] table-fixed">
            <colgroup>
              {showAgent && <col className="w-[108px]" />}
              <col className="w-[102px]" />
              <col className="w-[126px]" />
              <col className="w-[360px]" />
              <col className="w-[88px]" />
              <col className="w-[96px]" />
              <col className="w-[94px]" />
              <col className="w-[144px]" />
            </colgroup>
            <thead>
              <tr>
                {showAgent && <th>{t("common.agent")}</th>}
                <th>{t("tasks.table.headers.task")}</th>
                <th>{t("tasks.table.headers.status")}</th>
                <th>{t("tasks.table.headers.query")}</th>
                <th className="text-right">{t("tasks.table.headers.cost")}</th>
                <th className="text-right">{t("tasks.table.headers.duration")}</th>
                <th className="text-right">{t("tasks.table.headers.attempts")}</th>
                <th className="text-right">{t("tasks.table.headers.created")}</th>
              </tr>
            </thead>
            <tbody>
              {loading &&
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={colCount} />)}
              {!loading &&
                tasks.map((task) => {
                  const sessionLabel = formatSession(task.session_id);
                  const isSelected = selectedTaskId === task.id;

                  return (
                    <tr
                      key={`${task.agentId ?? "default"}-${task.id}`}
                      onClick={() => onTaskClick?.(task)}
                      className={cn(
                        "group transition-[background-color,border-color,box-shadow] duration-150",
                        isSelected && "bg-[var(--surface-tint)]",
                        onTaskClick && "cursor-pointer"
                      )}
                    >
                      {showAgent && (
                        <td>
                          {task.agentId ? (
                            <span
                              className="inline-flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold tracking-[0.06em] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
                              style={{
                                backgroundColor: `${getAgentColor(task.agentId)}10`,
                                color: getAgentColor(task.agentId),
                                borderColor: `${getAgentColor(task.agentId)}22`,
                              }}
                            >
                              <span
                                className="h-1.5 w-1.5 rounded-full"
                                style={{ backgroundColor: getAgentColor(task.agentId) }}
                              />
                              <span className="truncate">{task.agentId}</span>
                            </span>
                          ) : (
                            <span className="text-subtle">{"\u2014"}</span>
                          )}
                        </td>
                      )}
                      <td>
                        <div className="space-y-1">
                          <p className="font-mono text-xs text-foreground">#{task.id}</p>
                          <p className="truncate text-[11px] text-[var(--text-quaternary)]">
                            {t("tasks.table.chat", { value: task.chat_id })}
                          </p>
                        </div>
                      </td>
                      <td>
                        <StatusPill status={task.status} />
                      </td>
                      <td>
                        <div className="max-w-full space-y-1.5">
                          <p
                            className="line-clamp-3 text-sm leading-7 text-[var(--text-primary)] transition-colors group-hover:text-[var(--text-primary)]"
                            title={task.query_text ?? t("tasks.table.noDescription")}
                          >
                            {task.query_text || t("tasks.table.noDescription")}
                          </p>
                          <div className="flex max-w-full flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                            <span className="inline-flex max-w-[156px] items-center truncate rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                              {task.model ?? t("tasks.table.noModel")}
                            </span>
                            {sessionLabel && (
                              <span className="max-w-[160px] truncate font-mono text-[10px] text-[var(--text-quaternary)]">
                                {t("tasks.table.session", { value: sessionLabel })}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="text-right">
                        <p className="font-mono text-xs tabular-nums text-[var(--text-primary)]">
                          {formatCost(task.cost_usd)}
                        </p>
                      </td>
                      <td className="text-right">
                        <p
                          className="font-mono text-xs tabular-nums"
                          style={getSemanticTextStyle(getDurationTone(task.started_at, task.completed_at))}
                        >
                          {computeDuration(task.started_at, task.completed_at)}
                        </p>
                      </td>
                      <td className="text-right">
                        <p className="font-mono text-xs tabular-nums text-[var(--text-secondary)]">
                          {task.attempt}/{task.max_attempts}
                        </p>
                      </td>
                      <td className="text-right">
                        <div className="space-y-1 whitespace-nowrap">
                          <p
                            className="text-xs text-[var(--text-secondary)]"
                            title={formatDateTime(task.created_at)}
                          >
                            {formatRelativeTime(task.created_at)}
                          </p>
                          <p className="truncate text-[11px] text-[var(--text-quaternary)]">
                            {formatDateTime(task.created_at)}
                          </p>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              {tasks.length === 0 && !loading && (
                <tr>
                  <td colSpan={showAgent ? 8 : 7}>
                    <div className="empty-state">
                      <ListTodo className="empty-state-icon h-10 w-10" />
                      <p className="empty-state-text">{t("tasks.table.noTasksFound")}</p>
                      <p className="empty-state-subtext">
                        {t("tasks.table.adjustFilters")}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-3 p-4 md:hidden">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="app-card-row space-y-3">
              <div className="skeleton skeleton-text w-20" />
              <div className="skeleton skeleton-heading w-full" />
              <div className="skeleton skeleton-text w-32" />
            </div>
          ))}
        {!loading &&
          tasks.map((task) => (
            <button
              key={`${task.agentId ?? "default"}-${task.id}`}
              type="button"
              onClick={() => onTaskClick?.(task)}
              className={cn(
                "app-card-row app-card-row--interactive block w-full text-left",
                selectedTaskId === task.id &&
                  "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.028)]"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill status={task.status} />
                    {showAgent && task.agentId && (
                      <span
                        className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em]"
                        style={{
                          backgroundColor: `${getAgentColor(task.agentId)}12`,
                          color: getAgentColor(task.agentId),
                          borderColor: `${getAgentColor(task.agentId)}20`,
                        }}
                      >
                        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: getAgentColor(task.agentId) }} />
                        {task.agentId}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                    <span className="font-mono">#{task.id}</span>
                    <span className="h-1 w-1 rounded-full bg-[var(--border-strong)]" />
                    <span>{formatRelativeTime(task.created_at)}</span>
                  </div>
                  <p className="line-clamp-2 text-sm leading-6 text-[var(--text-primary)]">
                    {task.query_text || t("tasks.table.noDescription")}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                    <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                      {task.model ?? t("tasks.table.noModel")}
                    </span>
                    {task.session_id && (
                      <span className="font-mono text-[10px] text-[var(--text-quaternary)]">
                        {t("tasks.table.session", { value: formatSession(task.session_id) })}
                      </span>
                    )}
                  </div>
                </div>
                <ArrowUpRight className="mt-0.5 h-4 w-4 text-[var(--text-quaternary)]" />
              </div>

              <div className="mt-4 grid grid-cols-3 gap-3 text-[12px]">
                <MobileStat label={t("tasks.table.headers.cost")} value={formatCost(task.cost_usd)} mono />
                <MobileStat label={t("tasks.table.headers.duration")} value={computeDuration(task.started_at, task.completed_at)} mono />
                <MobileStat label={t("tasks.table.headers.attempts")} value={`${task.attempt}/${task.max_attempts}`} mono />
              </div>
            </button>
          ))}
        {tasks.length === 0 && !loading && (
          <div className="empty-state">
            <ListTodo className="empty-state-icon h-10 w-10" />
            <p className="empty-state-text">{t("tasks.table.noTasksFound")}</p>
            <p className="empty-state-subtext">
              {t("tasks.table.futureActivity")}
            </p>
          </div>
        )}
      </div>
    </>
  );
}

function MobileStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-3 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">{label}</p>
      <p className={cn("mt-1.5 text-[12px] text-[var(--text-secondary)]", mono && "font-mono tabular-nums")}>
        {mono ? truncateText(value, 22) : value}
      </p>
    </div>
  );
}
