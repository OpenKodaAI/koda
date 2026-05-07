"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatDuration } from "@/lib/utils";
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
            : execution.status === "paused"
              ? t("chat.toolCall.paused", { defaultValue: "Paused" })
              : execution.status === "cancelled"
                ? t("chat.toolCall.cancelled", { defaultValue: "Cancelled" })
                : t("chat.toolCall.queued", { defaultValue: "Queued" });

  const durationLabel =
    typeof execution.duration_ms === "number" && execution.duration_ms > 0
      ? formatDuration(execution.duration_ms)
      : null;

  const trailingLabel = durationLabel
    ? `${statusLabel} · ${durationLabel}`
    : statusLabel;

  const metadataItems: Array<{ label: string; value: string }> = [
    {
      label: t("chat.toolCall.task", { defaultValue: "task" }),
      value: `#${execution.task_id}`,
    },
    {
      label: t("chat.toolCall.status", { defaultValue: "status" }),
      value: statusLabel,
    },
  ];

  if (durationLabel) {
    metadataItems.push({
      label: t("chat.toolCall.duration", { defaultValue: "duration" }),
      value: durationLabel,
    });
  }
  if (typeof execution.tool_count === "number") {
    metadataItems.push({
      label: t("chat.toolCall.tools", { defaultValue: "tools" }),
      value: String(execution.tool_count),
    });
  }
  if (typeof execution.cost_usd === "number") {
    metadataItems.push({
      label: t("chat.toolCall.cost", { defaultValue: "cost" }),
      value: `$${execution.cost_usd.toFixed(4)}`,
    });
  }
  if (execution.model) {
    metadataItems.push({
      label: t("chat.toolCall.model", { defaultValue: "model" }),
      value: execution.model,
    });
  }
  if (typeof execution.attempt === "number" && typeof execution.max_attempts === "number") {
    metadataItems.push({
      label: t("chat.toolCall.attempt", { defaultValue: "attempt" }),
      value: `${execution.attempt}/${execution.max_attempts}`,
    });
  }

  return (
    <div className="pt-0.5 text-[0.75rem] text-[var(--text-quaternary)]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="inline-flex max-w-full items-center gap-1.5 rounded-[var(--radius-chip)] py-1 pr-1.5 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-[var(--text-secondary)]"
      >
        <ChevronRight
          className={cn(
            "h-3 w-3 shrink-0 transition-transform duration-[200ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            expanded && "rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
        <StatusDot tone={tone} pulse={isRunning} className="opacity-80" />
        <span className="truncate">
          {t("chat.toolCall.metadata", { defaultValue: "Metadata" })}
        </span>
        <span aria-hidden className="text-[var(--text-quaternary)]">
          ·
        </span>
        <span className="shrink-0 font-mono text-[0.6875rem]">{trailingLabel}</span>
      </button>

      {expanded ? (
        <div className="ml-4 mt-1 flex flex-col gap-2 border-l border-[color:var(--divider-hair)] pl-3">
          {execution.error_message ? (
            <pre className="m-0 max-h-[160px] overflow-auto rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] p-2.5 font-mono text-[0.75rem] leading-[1.45] text-[var(--tone-danger-text)] whitespace-pre-wrap">
              {execution.error_message}
            </pre>
          ) : null}
          <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[0.6875rem]">
            {metadataItems.map((item) => (
              <span key={`${item.label}-${item.value}`}>
                {item.label}:{" "}
                <span className="text-[var(--text-secondary)]">{item.value}</span>
              </span>
            ))}
          </div>
          <div className="flex justify-start">
            {onOpenDetails ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenDetails(execution.task_id);
                }}
                className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] py-0.5 pr-1.5 text-[0.75rem] text-[var(--accent)] transition-colors hover:text-[var(--text-primary)]"
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
