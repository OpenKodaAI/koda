"use client";

import { useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import { StatusDot } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  getExecutionMetadataVisual,
  getExecutionStatusVisual,
  type RuntimeVisualDescriptor,
} from "@/lib/runtime-visual-taxonomy";
import { cn, formatDuration } from "@/lib/utils";
import type { ExecutionSummary } from "@/lib/types";

interface ToolCallCardProps {
  execution: ExecutionSummary;
  onOpenDetails?: (taskId: number) => void;
}

export function ToolCallCard({ execution, onOpenDetails }: ToolCallCardProps) {
  const { t } = useAppI18n();
  const [expanded, setExpanded] = useState(false);
  const statusVisual = getExecutionStatusVisual(execution.status);
  const tone = statusVisual.tone;
  const isRunning =
    execution.status === "running" ||
    execution.status === "retrying" ||
    execution.status === "stalled";

  const statusLabel =
    execution.status === "running"
      ? t("chat.toolCall.running", { defaultValue: "Running" })
      : execution.status === "retrying"
        ? t("chat.toolCall.retrying", { defaultValue: "Retrying" })
        : execution.status === "stalled"
          ? t("chat.toolCall.stalled", { defaultValue: "Stalled" })
          : execution.status === "degraded"
            ? t("chat.toolCall.degraded", { defaultValue: "Degraded" })
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

  const metadataItems: Array<{ label: string; value: string; visual: RuntimeVisualDescriptor }> = [
    {
      label: t("chat.toolCall.task", { defaultValue: "task" }),
      value: `#${execution.task_id}`,
      visual: getExecutionMetadataVisual("task"),
    },
    {
      label: t("chat.toolCall.status", { defaultValue: "status" }),
      value: statusLabel,
      visual: statusVisual,
    },
  ];

  if (durationLabel) {
    metadataItems.push({
      label: t("chat.toolCall.duration", { defaultValue: "duration" }),
      value: durationLabel,
      visual: getExecutionMetadataVisual("duration"),
    });
  }
  if (typeof execution.tool_count === "number") {
    metadataItems.push({
      label: t("chat.toolCall.tools", { defaultValue: "tools" }),
      value: String(execution.tool_count),
      visual: getExecutionMetadataVisual("tools"),
    });
  }
  if (typeof execution.cost_usd === "number") {
    metadataItems.push({
      label: t("chat.toolCall.cost", { defaultValue: "cost" }),
      value: `$${execution.cost_usd.toFixed(4)}`,
      visual: getExecutionMetadataVisual("cost"),
    });
  }
  if (execution.model) {
    metadataItems.push({
      label: t("chat.toolCall.model", { defaultValue: "model" }),
      value: execution.model,
      visual: getExecutionMetadataVisual("model"),
    });
  }
  if (typeof execution.attempt === "number" && typeof execution.max_attempts === "number") {
    metadataItems.push({
      label: t("chat.toolCall.attempt", { defaultValue: "attempt" }),
      value: `${execution.attempt}/${execution.max_attempts}`,
      visual: getExecutionMetadataVisual("attempts"),
    });
  }

  return (
    <div className="pt-0.5 text-[0.6875rem] text-[var(--text-quaternary)]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="inline-flex max-w-full items-center gap-1.5 rounded-[var(--radius-chip)] py-0.5 pr-1 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-[var(--text-tertiary)]"
      >
        <ChevronRight
          className={cn(
            "h-2.5 w-2.5 shrink-0 opacity-60 transition-transform duration-[200ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            expanded && "rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
        <StatusDot tone={tone} pulse={isRunning} className="opacity-70" />
        <span className="truncate text-[var(--text-tertiary)]">
          {t("chat.toolCall.metadata", { defaultValue: "Metadata" })}
        </span>
        <span aria-hidden className="text-[var(--text-quaternary)]">
          ·
        </span>
        <span className="shrink-0 font-mono">{trailingLabel}</span>
      </button>

      {expanded ? (
        <div className="ml-5 mt-0.5 flex flex-col gap-1.5">
          {execution.error_message ? (
            <pre className="m-0 max-h-[140px] overflow-auto rounded-[var(--radius-panel-sm)] border border-[color:var(--divider-hair)] bg-[var(--panel-soft)]/45 p-2 font-mono text-[0.6875rem] leading-[1.45] text-[var(--tone-danger-muted)] whitespace-pre-wrap">
              {execution.error_message}
            </pre>
          ) : null}
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 font-mono text-[0.6875rem]">
            {metadataItems.map((item) => {
              const Icon = item.visual.icon;
              return (
                <span
                  key={`${item.label}-${item.value}`}
                  className="inline-flex items-center gap-1 text-[var(--text-quaternary)]"
                  data-metadata-visual={item.visual.key}
                >
                  <Icon className="h-2.5 w-2.5 opacity-60" strokeWidth={1.75} aria-hidden="true" />
                  <span className="opacity-80">{item.label}:</span>
                  <span className="text-[var(--text-tertiary)]">{item.value}</span>
                </span>
              );
            })}
          </div>
          <div className="flex justify-start pt-0.5">
            {onOpenDetails ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenDetails(execution.task_id);
                }}
                className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] py-0.5 pr-1.5 text-[0.6875rem] text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-secondary)]"
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
