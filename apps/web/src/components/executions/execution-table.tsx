"use client";

import { useMemo } from "react";
import { Workflow } from "lucide-react";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import type { StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ExecutionSummary } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
} from "@/lib/utils";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import { ExecutionStatusPill } from "./execution-status-pill";
import {
  EXECUTION_TONE_BG,
  EXECUTION_TONE_DOT,
  executionStatusTone,
} from "./execution-status";

interface ExecutionTableProps {
  executions: ExecutionSummary[];
  showAgent?: boolean;
  loading?: boolean;
  onExecutionClick?: (execution: ExecutionSummary) => void;
  selectedExecutionId?: number | null;
}

function ActivityBars({
  count,
  total,
  tone,
}: {
  count: number;
  total: number;
  tone: StatusDotTone;
}) {
  const segments = 8;
  const filled =
    total > 0
      ? Math.max(0, Math.min(segments, Math.round((count / total) * segments)))
      : 0;
  const dotColor = EXECUTION_TONE_DOT[tone];
  return (
    <span className="inline-flex items-center gap-[3px]" aria-hidden>
      {Array.from({ length: segments }).map((_, idx) => {
        const on = idx < filled;
        return (
          <span
            key={idx}
            className="block h-3 w-[3px] rounded-[1px]"
            style={{ background: on ? dotColor : "var(--panel-strong)" }}
          />
        );
      })}
    </span>
  );
}

function StatusOverlay({ tone }: { tone: StatusDotTone }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute inset-y-0 right-0 w-[34%]"
      style={{
        background: `linear-gradient(to left, color-mix(in srgb, ${EXECUTION_TONE_BG[tone]} 65%, transparent), transparent)`,
      }}
    />
  );
}

function SkeletonDesktopRow({
  cols,
  showAgent,
}: {
  cols: string;
  showAgent: boolean;
}) {
  return (
    <div
      className={cn(
        "grid items-center gap-4 px-4 py-3 border-b border-[color:var(--divider-hair)] last:border-b-0",
        cols,
      )}
    >
      <div className="h-3 w-6 rounded bg-[var(--panel-soft)] animate-pulse" />
      {showAgent ? (
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-full bg-[var(--panel-soft)] animate-pulse" />
          <div className="flex flex-col gap-1">
            <div className="h-3 w-20 rounded bg-[var(--panel-soft)] animate-pulse" />
            <div className="h-2 w-12 rounded bg-[var(--panel-soft)] animate-pulse" />
          </div>
        </div>
      ) : null}
      <div className="h-3 w-[70%] rounded bg-[var(--panel-soft)] animate-pulse" />
      <div className="h-3 w-16 rounded bg-[var(--panel-soft)] animate-pulse" />
      <div className="ml-auto h-3 w-12 rounded bg-[var(--panel-soft)] animate-pulse" />
      <div className="ml-auto h-3 w-12 rounded bg-[var(--panel-soft)] animate-pulse" />
      <div className="ml-auto h-3 w-16 rounded bg-[var(--panel-soft)] animate-pulse" />
      <div className="ml-auto h-5 w-20 rounded-[var(--radius-chip)] bg-[var(--panel-soft)] animate-pulse" />
    </div>
  );
}

function MobileSkeletonCard({ showAgent }: { showAgent: boolean }) {
  return (
    <div className="flex animate-pulse flex-col gap-2 border-b border-[color:var(--divider-hair)] px-4 py-3 last:border-b-0">
      <div className="flex items-center gap-3">
        <div className="h-3 w-6 rounded bg-[var(--panel-soft)]" />
        {showAgent ? (
          <div className="h-7 w-7 rounded-full bg-[var(--panel-soft)]" />
        ) : null}
        <div className="h-3 w-24 rounded bg-[var(--panel-soft)]" />
        <div className="ml-auto h-5 w-16 rounded-[var(--radius-chip)] bg-[var(--panel-soft)]" />
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

  const maxTools = useMemo(
    () =>
      executions.reduce(
        (max, exec) => Math.max(max, exec.tool_count ?? 0),
        0,
      ),
    [executions],
  );

  const cols = showAgent
    ? "grid-cols-[40px_minmax(180px,200px)_minmax(0,1fr)_104px_84px_84px_92px_124px]"
    : "grid-cols-[40px_minmax(0,1fr)_104px_84px_84px_92px_124px]";

  const getStatusLabel = (status: string) =>
    t(`runtime.labels.${status}`, { defaultValue: status });

  const headerClass =
    "px-1 font-mono text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]";

  return (
    <div className="overflow-hidden rounded-[var(--radius-shell)] border border-[color:var(--border-subtle)] bg-[var(--panel)]">
      {/* Desktop */}
      <div className="hidden md:block">
        {/* Column header */}
        <div
          className={cn(
            "grid items-center gap-4 border-b border-[color:var(--divider-hair)] px-4 py-2.5",
            cols,
          )}
          role="row"
        >
          <span className={headerClass}>#</span>
          {showAgent ? (
            <span className={headerClass}>{t("common.agent")}</span>
          ) : null}
          <span className={headerClass}>
            {t("executions.table.queryColumn")}
          </span>
          <span className={headerClass}>{t("executions.table.tools")}</span>
          <span className={cn(headerClass, "text-right")}>
            {t("common.cost")}
          </span>
          <span className={cn(headerClass, "text-right")}>
            {t("common.duration")}
          </span>
          <span className={cn(headerClass, "text-right")}>
            {t("common.created")}
          </span>
          <span className={cn(headerClass, "text-right")}>
            {t("common.status")}
          </span>
        </div>

        {/* Rows */}
        <div className="flex flex-col">
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <SkeletonDesktopRow
                key={i}
                cols={cols}
                showAgent={showAgent}
              />
            ))}

          {!loading &&
            executions.map((execution, index) => {
              const tone = executionStatusTone(execution.status);
              const isSelected =
                selectedExecutionId === execution.task_id;
              return (
                <button
                  key={`${execution.bot_id}-${execution.task_id}`}
                  type="button"
                  onClick={() => onExecutionClick?.(execution)}
                  className={cn(
                    "group relative grid w-full items-center gap-4 px-4 py-3 text-left",
                    "border-b border-[color:var(--divider-hair)] last:border-b-0",
                    "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)] focus-visible:ring-inset",
                    onExecutionClick && "cursor-pointer",
                    isSelected
                      ? "bg-[var(--hover-tint)]"
                      : onExecutionClick && "hover:bg-[var(--hover-tint)]",
                    cols,
                  )}
                >
                  <StatusOverlay tone={tone} />

                  {/* # index */}
                  <span className="relative font-mono text-[0.875rem] tabular-nums text-[var(--text-quaternary)]">
                    {String(index + 1).padStart(2, "0")}
                  </span>

                  {/* Agent (orb + name + #task_id) */}
                  {showAgent ? (
                    <span className="relative flex min-w-0 items-center gap-2.5">
                      <AgentSigil
                        agentId={execution.bot_id}
                        label={getAgentLabel(execution.bot_id)}
                        color={getAgentColor(execution.bot_id)}
                        status={execution.status}
                        size="xs"
                      />
                      <span className="flex min-w-0 flex-col leading-tight">
                        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                          {getAgentLabel(execution.bot_id)}
                        </span>
                        <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                          #{execution.task_id}
                        </span>
                      </span>
                    </span>
                  ) : null}

                  {/* Action / query */}
                  <p
                    className="relative m-0 line-clamp-1 text-[0.8125rem] text-[var(--text-primary)]"
                    title={
                      execution.query_text ?? t("executions.table.noQuery")
                    }
                  >
                    {execution.query_text ||
                      t("executions.table.noQueryRegistered")}
                  </p>

                  {/* Tools — bars + count */}
                  <span className="relative inline-flex items-center gap-2">
                    <ActivityBars
                      count={execution.tool_count ?? 0}
                      total={maxTools}
                      tone={tone}
                    />
                    <span className="font-mono text-[0.6875rem] tabular-nums text-[var(--text-secondary)]">
                      {execution.tool_count ?? 0}
                    </span>
                  </span>

                  {/* Cost */}
                  <span className="relative text-right font-mono text-[0.75rem] tabular-nums text-[var(--text-secondary)]">
                    {formatCost(execution.cost_usd)}
                  </span>

                  {/* Duration */}
                  <span className="relative text-right font-mono text-[0.75rem] tabular-nums text-[var(--text-secondary)]">
                    {formatDuration(execution.duration_ms)}
                  </span>

                  {/* Created */}
                  <span
                    className="relative text-right font-mono text-[0.75rem] tabular-nums text-[var(--text-secondary)]"
                    title={formatDateTime(execution.created_at)}
                  >
                    {formatRelativeTime(execution.created_at)}
                  </span>

                  {/* Status badge */}
                  <span className="relative flex justify-end">
                    <ExecutionStatusPill
                      status={execution.status}
                      label={getStatusLabel(execution.status)}
                    />
                  </span>
                </button>
              );
            })}

          {executions.length === 0 && !loading && (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
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
      </div>

      {/* Mobile */}
      <div className="flex flex-col md:hidden">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <MobileSkeletonCard key={i} showAgent={showAgent} />
          ))}

        {!loading &&
          executions.map((execution, index) => {
            const tone = executionStatusTone(execution.status);
            const isSelected = selectedExecutionId === execution.task_id;
            return (
              <button
                key={`${execution.bot_id}-${execution.task_id}`}
                type="button"
                onClick={() => onExecutionClick?.(execution)}
                className={cn(
                  "relative flex w-full flex-col gap-2 border-b border-[color:var(--divider-hair)] px-4 py-3 text-left",
                  "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] last:border-b-0",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)] focus-visible:ring-inset",
                  isSelected
                    ? "bg-[var(--hover-tint)]"
                    : onExecutionClick && "hover:bg-[var(--hover-tint)]",
                )}
              >
                <StatusOverlay tone={tone} />

                <div className="relative flex items-center gap-3">
                  <span className="font-mono text-[0.75rem] tabular-nums text-[var(--text-quaternary)]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {showAgent ? (
                    <AgentSigil
                      agentId={execution.bot_id}
                      label={getAgentLabel(execution.bot_id)}
                      color={getAgentColor(execution.bot_id)}
                      status={execution.status}
                      size="xs"
                    />
                  ) : null}
                  <div className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                      {showAgent
                        ? getAgentLabel(execution.bot_id)
                        : `#${execution.task_id}`}
                    </span>
                    {showAgent ? (
                      <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                        #{execution.task_id}
                      </span>
                    ) : null}
                  </div>
                  <ExecutionStatusPill
                    status={execution.status}
                    label={getStatusLabel(execution.status)}
                  />
                </div>

                <p className="relative m-0 line-clamp-2 text-[var(--font-size-sm)] leading-[1.5] text-[var(--text-primary)]">
                  {execution.query_text ||
                    t("executions.table.noQueryRegistered")}
                </p>

                <div className="relative flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  <span className="inline-flex items-center gap-1.5">
                    <ActivityBars
                      count={execution.tool_count ?? 0}
                      total={maxTools}
                      tone={tone}
                    />
                    <span className="text-[var(--text-secondary)]">
                      {execution.tool_count ?? 0}
                    </span>
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
                  <span className="ml-auto text-[var(--text-quaternary)]">
                    {formatRelativeTime(execution.created_at)}
                  </span>
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
    </div>
  );
}
