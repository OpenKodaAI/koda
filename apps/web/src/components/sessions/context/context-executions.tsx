"use client";

import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ExecutionSummary, Task } from "@/lib/types";
import { formatCost, formatRelativeTime, truncateText } from "@/lib/utils";

type TaskStatus = Task["status"];
type ExecutionSummaryLike = ExecutionSummary & { agent_id?: string | null };

interface ContextExecutionsProps {
  executions: ExecutionSummaryLike[];
  maxItems?: number;
  onOpenExecution?: (taskId: number, agentId: string | null) => void;
}

const STATUS_TONE: Record<TaskStatus, StatusDotTone> = {
  queued: "neutral",
  running: "info",
  retrying: "warning",
  completed: "success",
  failed: "danger",
  paused: "warning",
  cancelled: "neutral",
};

function toneFor(status: TaskStatus | null | undefined): StatusDotTone {
  if (!status) return "neutral";
  return STATUS_TONE[status] ?? "neutral";
}

function isRunning(status: TaskStatus | null | undefined) {
  return status === "running" || status === "retrying";
}

export function ContextExecutions({
  executions,
  maxItems = 5,
  onOpenExecution,
}: ContextExecutionsProps) {
  const { t } = useAppI18n();
  const visible = executions.slice(0, maxItems);

  return (
    <section className="px-5 py-5">
      <h4 className="m-0 mb-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {t("sessions.context.recentExecutions", { defaultValue: "Recent executions" })}
      </h4>
      {visible.length === 0 ? (
        <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("sessions.context.noExecutions", { defaultValue: "No linked executions yet." })}
        </p>
      ) : (
        <ol className="flex flex-col">
          {visible.map((execution) => {
            const tone = toneFor(execution.status);
            const running = isRunning(execution.status);
            const label =
              execution.query_text?.trim() ||
              t("sessions.context.artifacts.executionFallback", { defaultValue: "Execution" });
            const executionBotId = execution.bot_id ?? execution.agent_id ?? null;
            const handleOpen = onOpenExecution
              ? () => onOpenExecution(execution.task_id, executionBotId)
              : undefined;

            return (
              <li
                key={execution.task_id}
                className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-[color:var(--divider-hair)] py-2.5 last:border-b-0"
              >
                <StatusDot tone={tone} pulse={running} />
                <button
                  type="button"
                  onClick={handleOpen}
                  disabled={!handleOpen}
                  className="flex min-w-0 flex-col items-start gap-0.5 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-[var(--text-primary)] disabled:cursor-default"
                >
                  <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">
                    <span className="font-mono text-[var(--text-quaternary)]">
                      #{execution.task_id}
                    </span>
                    {" · "}
                    {truncateText(label, 40)}
                  </span>
                  <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                    {formatRelativeTime(
                      execution.completed_at || execution.started_at || execution.created_at,
                    )}
                  </span>
                </button>
                <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-secondary)]">
                  {formatCost(execution.cost_usd)}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
