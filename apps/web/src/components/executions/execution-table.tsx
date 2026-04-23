"use client";

import { Workflow } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ExecutionSummary, Task } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
} from "@/lib/utils";
import { getAgentColor } from "@/lib/agent-constants";

interface ExecutionTableProps {
  executions: ExecutionSummary[];
  showAgent?: boolean;
  loading?: boolean;
  onExecutionClick?: (execution: ExecutionSummary) => void;
  selectedExecutionId?: number | null;
}

type TaskStatus = Task["status"];

const STATUS_TONE: Record<TaskStatus, StatusDotTone> = {
  queued: "neutral",
  running: "info",
  retrying: "warning",
  completed: "success",
  failed: "danger",
  paused: "warning",
  cancelled: "neutral",
};

const TRACE_TONE: Record<ExecutionSummary["trace_source"], StatusDotTone> = {
  trace: "success",
  legacy: "warning",
  missing: "neutral",
};

function statusTone(status: string): StatusDotTone {
  return STATUS_TONE[status as TaskStatus] ?? "neutral";
}

function isRunning(status: string) {
  return status === "running" || status === "retrying";
}

function SkeletonRow({ showAgent }: { showAgent: boolean }) {
  return (
    <tr className="animate-pulse">
      {showAgent ? (
        <td className="py-3 pr-4">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-[var(--panel-strong)]" />
            <div className="h-3 w-20 rounded bg-[var(--panel-soft)]" />
          </div>
        </td>
      ) : null}
      <td className="py-3 pr-4">
        <div className="h-3 w-14 rounded bg-[var(--panel-soft)]" />
      </td>
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-[var(--panel-strong)]" />
          <div className="h-3 w-20 rounded bg-[var(--panel-soft)]" />
        </div>
      </td>
      <td className="py-3 pr-4">
        <div className="h-3 w-[70%] rounded bg-[var(--panel-soft)]" />
      </td>
      <td className="py-3 pr-4">
        <div className="h-1.5 w-1.5 rounded-full bg-[var(--panel-strong)]" />
      </td>
      <td className="py-3 pr-4 text-right">
        <div className="ml-auto h-3 w-14 rounded bg-[var(--panel-soft)]" />
      </td>
      <td className="py-3 pr-4 text-right">
        <div className="ml-auto h-3 w-14 rounded bg-[var(--panel-soft)]" />
      </td>
      <td className="py-3 text-right">
        <div className="ml-auto h-3 w-20 rounded bg-[var(--panel-soft)]" />
      </td>
    </tr>
  );
}

function MobileSkeletonCard({ showAgent }: { showAgent: boolean }) {
  return (
    <div className="flex animate-pulse flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 last:border-b-0">
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-1.5 rounded-full bg-[var(--panel-strong)]" />
        <div className="h-3 w-16 rounded bg-[var(--panel-soft)]" />
        {showAgent ? <div className="h-3 w-20 rounded bg-[var(--panel-soft)]" /> : null}
      </div>
      <div className="h-3 w-full rounded bg-[var(--panel-soft)]" />
      <div className="h-3 w-2/3 rounded bg-[var(--panel-soft)]" />
    </div>
  );
}

export function ExecutionTable({
  executions,
  showAgent = false,
  loading = false,
  onExecutionClick,
  selectedExecutionId,
}: ExecutionTableProps) {
  const { t } = useAppI18n();
  const getStatusLabel = (status: string) =>
    t(`runtime.labels.${status}`, { defaultValue: status });
  const traceLabel: Record<ExecutionSummary["trace_source"], string> = {
    trace: t("executions.table.richTrace"),
    legacy: t("executions.table.rebuilt"),
    missing: t("executions.table.noTrace"),
  };

  const thClass =
    "py-2.5 pr-4 text-left font-mono text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]";
  const thRightClass = `${thClass} text-right`;

  return (
    <>
      <div className="hidden md:block">
        <div className="max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain">
          <table className="w-full table-fixed">
            <colgroup>
              {showAgent && <col className="w-[108px]" />}
              <col className="w-[92px]" />
              <col className="w-[128px]" />
              <col className="w-[360px]" />
              <col className="w-[112px]" />
              <col className="w-[88px]" />
              <col className="w-[94px]" />
              <col className="w-[148px]" />
            </colgroup>
            <thead>
              <tr className="border-b border-[color:var(--divider-hair)]">
                {showAgent && <th className={thClass}>{t("common.agent")}</th>}
                <th className={thClass}>{t("executions.table.execution")}</th>
                <th className={thClass}>{t("common.status")}</th>
                <th className={thClass}>{t("executions.table.queryColumn")}</th>
                <th className={thClass}>{t("executions.table.trace")}</th>
                <th className={thRightClass}>{t("common.cost")}</th>
                <th className={thRightClass}>{t("common.duration")}</th>
                <th className={thRightClass}>{t("common.created")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--divider-hair)]">
              {loading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonRow key={i} showAgent={showAgent} />
                ))}
              {!loading &&
                executions.map((execution) => {
                  const isSelected = selectedExecutionId === execution.task_id;
                  return (
                    <tr
                      key={`${execution.bot_id}-${execution.task_id}`}
                      onClick={() => onExecutionClick?.(execution)}
                      className={cn(
                        "group transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        onExecutionClick && "cursor-pointer",
                        isSelected
                          ? "bg-[var(--hover-tint)]"
                          : onExecutionClick && "hover:bg-[var(--hover-tint)]",
                      )}
                    >
                      {showAgent && (
                        <td className="py-3 pr-4">
                          <span className="inline-flex items-center gap-1.5">
                            <StatusDot color={getAgentColor(execution.bot_id)} />
                            <span className="truncate font-mono text-[0.75rem] text-[var(--text-secondary)]">
                              {execution.bot_id}
                            </span>
                          </span>
                        </td>
                      )}
                      <td className="py-3 pr-4">
                        <span className="font-mono text-[0.75rem] text-[var(--text-primary)]">
                          #{execution.task_id}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <span className="inline-flex items-center gap-1.5">
                          <StatusDot
                            tone={statusTone(execution.status)}
                            pulse={isRunning(execution.status)}
                          />
                          <span className="font-mono text-[0.75rem] text-[var(--text-secondary)]">
                            {getStatusLabel(execution.status)}
                          </span>
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <p
                          className="m-0 line-clamp-1 text-[0.8125rem] text-[var(--text-primary)]"
                          title={execution.query_text ?? t("executions.table.noQuery")}
                        >
                          {execution.query_text || t("executions.table.noQueryRegistered")}
                        </p>
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className="inline-flex items-center gap-1.5"
                          title={traceLabel[execution.trace_source]}
                        >
                          <StatusDot tone={TRACE_TONE[execution.trace_source]} />
                          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">
                            {traceLabel[execution.trace_source]}
                          </span>
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-right">
                        <p className="m-0 font-mono text-[0.75rem] tabular-nums text-[var(--text-primary)]">
                          {formatCost(execution.cost_usd)}
                        </p>
                      </td>
                      <td className="py-3 pr-4 text-right">
                        <p className="m-0 font-mono text-[0.75rem] tabular-nums text-[var(--text-secondary)]">
                          {formatDuration(execution.duration_ms)}
                        </p>
                      </td>
                      <td className="py-3 text-right">
                        <p
                          className="m-0 text-[0.75rem] text-[var(--text-secondary)]"
                          title={formatDateTime(execution.created_at)}
                        >
                          {formatRelativeTime(execution.created_at)}
                        </p>
                      </td>
                    </tr>
                  );
                })}
              {executions.length === 0 && !loading && (
                <tr>
                  <td colSpan={showAgent ? 8 : 7} className="py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <Workflow
                        className="icon-lg text-[var(--text-quaternary)]"
                        strokeWidth={1.5}
                        aria-hidden
                      />
                      <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
                        {t("executions.table.noResults")}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col md:hidden">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <MobileSkeletonCard key={i} showAgent={showAgent} />
          ))}
        {!loading &&
          executions.map((execution) => {
            const isSelected = selectedExecutionId === execution.task_id;
            return (
              <button
                key={`${execution.bot_id}-${execution.task_id}`}
                type="button"
                onClick={() => onExecutionClick?.(execution)}
                className={cn(
                  "flex w-full flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] last:border-b-0",
                  isSelected
                    ? "bg-[var(--hover-tint)]"
                    : onExecutionClick && "hover:bg-[var(--hover-tint)]",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-[0.75rem]">
                  <span className="inline-flex items-center gap-1.5">
                    <StatusDot
                      tone={statusTone(execution.status)}
                      pulse={isRunning(execution.status)}
                    />
                    <span className="font-mono text-[var(--text-secondary)]">
                      {getStatusLabel(execution.status)}
                    </span>
                  </span>
                  <span className="text-[var(--text-quaternary)]">·</span>
                  <span className="font-mono text-[var(--text-quaternary)]">
                    #{execution.task_id}
                  </span>
                  {showAgent ? (
                    <>
                      <span className="text-[var(--text-quaternary)]">·</span>
                      <span className="inline-flex items-center gap-1.5 font-mono text-[var(--text-secondary)]">
                        <StatusDot color={getAgentColor(execution.bot_id)} />
                        {execution.bot_id}
                      </span>
                    </>
                  ) : null}
                  <span className="ml-auto text-[var(--text-quaternary)]">
                    {formatRelativeTime(execution.created_at)}
                  </span>
                </div>
                <p className="m-0 line-clamp-2 text-[var(--font-size-sm)] leading-[1.5] text-[var(--text-primary)]">
                  {execution.query_text || t("executions.table.noQueryRegistered")}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  <span>
                    {t("executions.table.tools")}:{" "}
                    <span className="text-[var(--text-secondary)]">{execution.tool_count}</span>
                  </span>
                  <span>
                    {t("common.cost")}:{" "}
                    <span className="text-[var(--text-secondary)]">
                      {formatCost(execution.cost_usd)}
                    </span>
                  </span>
                  <span>
                    {t("common.duration")}:{" "}
                    <span className="text-[var(--text-secondary)]">
                      {formatDuration(execution.duration_ms)}
                    </span>
                  </span>
                  {execution.warning_count > 0 ? (
                    <span>
                      {t("executions.table.warnings")}:{" "}
                      <span className="text-[var(--tone-warning-dot)]">
                        {execution.warning_count}
                      </span>
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })}
        {executions.length === 0 && !loading && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <Workflow
              className="icon-lg text-[var(--text-quaternary)]"
              strokeWidth={1.5}
              aria-hidden
            />
            <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
              {t("executions.table.noResults")}
            </p>
          </div>
        )}
      </div>
    </>
  );
}
