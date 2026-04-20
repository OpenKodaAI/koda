"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatDuration, truncateText } from "@/lib/utils";
import type { ExecutionSummary } from "@/lib/types";

interface ToolCallCardProps {
  execution: ExecutionSummary;
  onOpenDetails?: (taskId: number) => void;
}

const STATUS_TONE: Record<ExecutionSummary["status"], StatusDotTone> = {
  queued: "neutral",
  running: "accent",
  retrying: "retry",
  completed: "success",
  failed: "danger",
  paused: "warning",
  cancelled: "neutral",
};

export function ToolCallCard({ execution, onOpenDetails }: ToolCallCardProps) {
  const { t } = useAppI18n();
  const [expanded, setExpanded] = useState(false);
  const tone = STATUS_TONE[execution.status];
  const isRunning = execution.status === "running" || execution.status === "retrying";

  const statusLabel =
    execution.status === "running"
      ? t("chat.toolCall.running", { defaultValue: "Running" })
      : execution.status === "retrying"
        ? t("chat.toolCall.retrying", { defaultValue: "Retrying" })
        : execution.status === "completed"
          ? t("chat.toolCall.completed", { defaultValue: "Completed" })
          : execution.status === "failed"
            ? t("chat.toolCall.failed", { defaultValue: "Failed" })
            : t("chat.toolCall.queued", { defaultValue: "Queued" });

  const durationLabel =
    typeof execution.duration_ms === "number" && execution.duration_ms > 0
      ? formatDuration(execution.duration_ms)
      : null;

  const trailingLabel = durationLabel
    ? `${statusLabel} · ${durationLabel}`
    : statusLabel;

  const summaryText =
    execution.query_text?.trim() ||
    (execution.error_message?.trim() ? execution.error_message.trim() : null);

  return (
    <div className="border-t border-[color:var(--divider-hair)]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="grid w-full grid-cols-[auto_1fr_auto_auto] items-center gap-3 py-2.5 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-[var(--text-primary)]"
      >
        <StatusDot tone={tone} pulse={isRunning} />
        <div className="min-w-0">
          <p className="m-0 truncate text-[0.8125rem] text-[var(--text-secondary)]">
            <span className="font-mono text-[var(--text-quaternary)]">
              #{execution.task_id}
            </span>
            {summaryText ? <> · {truncateText(summaryText, 56)}</> : null}
          </p>
        </div>
        <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          {trailingLabel}
        </span>
        <ChevronRight
          className={cn(
            "icon-xs text-[var(--text-quaternary)] transition-transform duration-[200ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            expanded && "rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
      </button>

      {expanded ? (
        <div className="flex flex-col gap-2 pb-3 pl-[18px] pr-1 pt-0">
          {execution.error_message ? (
            <pre className="m-0 max-h-[200px] overflow-auto rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] p-3 font-mono text-[0.75rem] leading-[1.45] text-[var(--tone-danger-text)] whitespace-pre-wrap">
              {execution.error_message}
            </pre>
          ) : null}
          {execution.query_text ? (
            <div>
              <p className="m-0 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                {t("chat.toolCall.viewArgs", { defaultValue: "Arguments" })}
              </p>
              <pre className="mt-1 max-h-[160px] overflow-auto rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] p-3 font-mono text-[0.75rem] leading-[1.45] text-[var(--text-secondary)] whitespace-pre-wrap">
                {execution.query_text}
              </pre>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {typeof execution.tool_count === "number" ? (
                <span>
                  {t("chat.toolCall.tools", { defaultValue: "tools" })}:{" "}
                  <span className="text-[var(--text-secondary)]">{execution.tool_count}</span>
                </span>
              ) : null}
              {typeof execution.cost_usd === "number" ? (
                <span>
                  {t("chat.toolCall.cost", { defaultValue: "cost" })}:{" "}
                  <span className="text-[var(--text-secondary)]">
                    ${execution.cost_usd.toFixed(4)}
                  </span>
                </span>
              ) : null}
              {execution.model ? (
                <span className="text-[var(--text-secondary)]">{execution.model}</span>
              ) : null}
            </div>
            {onOpenDetails ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenDetails(execution.task_id);
                }}
                className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] px-1.5 py-0.5 text-[0.75rem] text-[var(--accent)] transition-colors hover:bg-[var(--hover-tint)]"
              >
                {t("chat.toolCall.viewExecution", { defaultValue: "View execution" })}
                <ExternalLink className="icon-xs" strokeWidth={1.75} aria-hidden />
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
