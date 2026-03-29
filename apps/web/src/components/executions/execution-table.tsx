"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ExecutionSummary } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
  truncateText,
} from "@/lib/utils";
import { getBotColor } from "@/lib/bot-constants";
import { getSemanticStyle, getSemanticTextStyle, type SemanticTone } from "@/lib/theme-semantic";
import { Workflow } from "lucide-react";

interface ExecutionTableProps {
  executions: ExecutionSummary[];
  showBot?: boolean;
  loading?: boolean;
  onExecutionClick?: (execution: ExecutionSummary) => void;
  selectedExecutionId?: number | null;
}

function getDurationTone(durationMs: number | null): SemanticTone {
  if (durationMs == null) return "neutral";
  if (durationMs < 30000) return "success";
  if (durationMs <= 300000) return "warning";
  return "neutral";
}

function getStatusDotColor(status: string): string {
  const map: Record<string, string> = {
    completed: 'var(--status-completed)',
    running: 'var(--status-running)',
    queued: 'var(--status-queued)',
    failed: 'var(--status-failed)',
    retrying: 'var(--status-retrying)',
  };
  return map[status] ?? 'var(--text-quaternary)';
}

function SkeletonRow({ showBot }: { showBot: boolean }) {
  return (
    <tr className="animate-pulse">
      {showBot ? (
        <td>
          <div className="flex items-center gap-2">
            <div className="skeleton-circle h-2.5 w-2.5" />
            <div className="skeleton h-3 w-20 rounded-xl" />
          </div>
        </td>
      ) : null}
      <td>
        <div className="skeleton h-3 w-14 rounded-xl" />
      </td>
      <td>
        <div className="flex items-center gap-2">
          <div className="skeleton-circle h-2.5 w-2.5" />
          <div className="skeleton h-3 w-20 rounded-xl" />
        </div>
      </td>
      <td>
        <div className="space-y-2">
          <div className="skeleton h-3 w-[78%] rounded-xl" />
          <div className="skeleton h-3 w-[62%] rounded-xl" />
        </div>
      </td>
      <td>
        <div className="flex items-center gap-2">
          <div className="skeleton-circle h-2.5 w-2.5" />
          <div className="skeleton h-3 w-16 rounded-xl" />
        </div>
      </td>
      <td className="text-right">
        <div className="ml-auto skeleton h-3 w-16 rounded-xl" />
      </td>
      <td className="text-right">
        <div className="ml-auto skeleton h-3 w-14 rounded-xl" />
      </td>
      <td className="text-right">
        <div className="ml-auto space-y-2">
          <div className="ml-auto skeleton h-3 w-16 rounded-xl" />
          <div className="ml-auto skeleton h-3 w-24 rounded-xl" />
        </div>
      </td>
    </tr>
  );
}

function MobileSkeletonCard({ showBot }: { showBot: boolean }) {
  return (
    <div className="app-card-row space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2">
              <div className="skeleton-circle h-2.5 w-2.5" />
              <div className="skeleton h-3 w-16 rounded-xl" />
            </div>
            <div className="skeleton-circle h-2.5 w-2.5" />
            {showBot ? (
              <div className="flex items-center gap-2">
                <div className="skeleton-circle h-2.5 w-2.5" />
                <div className="skeleton h-3 w-20 rounded-xl" />
              </div>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <div className="skeleton h-3 w-12 rounded-xl" />
            <div className="skeleton-circle h-1.5 w-1.5" />
            <div className="skeleton h-3 w-16 rounded-xl" />
          </div>
          <div className="space-y-2">
            <div className="skeleton h-3 w-full rounded-xl" />
            <div className="skeleton h-3 w-[82%] rounded-xl" />
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2.5 text-[12px]">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="border-b border-[rgba(255,255,255,0.06)] px-0 py-2">
            <div className="skeleton h-2.5 w-14 rounded-xl" />
            <div className="mt-2 skeleton h-3 w-16 rounded-xl" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ExecutionTable({
  executions,
  showBot = false,
  loading = false,
  onExecutionClick,
  selectedExecutionId,
}: ExecutionTableProps) {
  const { t } = useAppI18n();
  const getStatusLabel = (status: string) =>
    t(`runtime.labels.${status}`, { defaultValue: status });
  const traceSourceMeta: Record<
    ExecutionSummary["trace_source"],
    { label: string; tone: SemanticTone }
  > = {
    trace: {
      label: t("executions.table.richTrace"),
      tone: "success",
    },
    legacy: {
      label: t("executions.table.rebuilt"),
      tone: "warning",
    },
    missing: {
      label: t("executions.table.noTrace"),
      tone: "neutral",
    },
  };

  return (
    <>
      <div className="hidden md:block">
        <div className="max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain">
          <table className="glass-table w-full table-fixed">
            <colgroup>
              {showBot && <col className="w-[108px]" />}
              <col className="w-[102px]" />
              <col className="w-[128px]" />
              <col className="w-[360px]" />
              <col className="w-[182px]" />
              <col className="w-[88px]" />
              <col className="w-[94px]" />
              <col className="w-[148px]" />
            </colgroup>
            <thead>
              <tr>
                {showBot && <th>{t("common.bot")}</th>}
                <th>{t("executions.table.execution")}</th>
                <th>{t("common.status")}</th>
                <th>{t("executions.table.queryColumn")}</th>
                <th>{t("executions.table.trace")}</th>
                <th className="text-right">{t("common.cost")}</th>
                <th className="text-right">{t("common.duration")}</th>
                <th className="text-right">{t("common.created")}</th>
              </tr>
            </thead>
            <tbody>
              {loading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonRow key={i} showBot={showBot} />
                ))}
              {!loading &&
                executions.map((execution) => {
                  const isSelected = selectedExecutionId === execution.task_id;

                  return (
                    <tr
                      key={`${execution.bot_id}-${execution.task_id}`}
                      onClick={() => onExecutionClick?.(execution)}
                      className={cn(
                        "group transition-[background-color,border-color,box-shadow] duration-150",
                        isSelected && "bg-[var(--table-row-selected)]",
                        onExecutionClick && "cursor-pointer"
                      )}
                    >
                      {showBot && (
                        <td>
                          <span className="inline-flex items-center gap-2 font-mono text-xs">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: getBotColor(execution.bot_id) }} />
                            <span className="truncate">{execution.bot_id}</span>
                          </span>
                        </td>
                      )}
                      <td>
                        <span className="font-mono text-xs text-foreground">#{execution.task_id}</span>
                      </td>
                      <td>
                        <span className="inline-flex items-center gap-2">
                          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: getStatusDotColor(execution.status) }} />
                          <span className="font-mono text-xs">{getStatusLabel(execution.status)}</span>
                        </span>
                      </td>
                      <td>
                        <p className="line-clamp-1 font-mono text-[13px] text-[var(--text-primary)]"
                           title={execution.query_text ?? t("executions.table.noQuery")}>
                          {execution.query_text || t("executions.table.noQueryRegistered")}
                        </p>
                      </td>
                      <td>
                        <span className="h-2 w-2 rounded-full" style={getSemanticStyle(traceSourceMeta[execution.trace_source].tone)} />
                      </td>
                      <td className="text-right">
                        <p className="font-mono text-xs tabular-nums text-[var(--text-primary)]">
                          {formatCost(execution.cost_usd)}
                        </p>
                      </td>
                      <td className="text-right">
                        <p
                          className="font-mono text-xs tabular-nums"
                          style={getSemanticTextStyle(getDurationTone(execution.duration_ms))}
                        >
                          {formatDuration(execution.duration_ms)}
                        </p>
                      </td>
                      <td className="text-right">
                        <div className="space-y-1 whitespace-nowrap">
                          <p
                            className="text-xs text-[var(--text-secondary)]"
                            title={formatDateTime(execution.created_at)}
                          >
                            {formatRelativeTime(execution.created_at)}
                          </p>
                          <p className="truncate text-[10.5px] text-[var(--text-quaternary)]">
                            {formatDateTime(execution.created_at)}
                          </p>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              {executions.length === 0 && !loading && (
                <tr>
                  <td colSpan={showBot ? 8 : 7}>
                      <div className="empty-state">
                        <Workflow className="empty-state-icon h-10 w-10" />
                        <p className="empty-state-text">{t("executions.table.noResults")}</p>
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
            <MobileSkeletonCard key={i} showBot={showBot} />
          ))}
        {!loading &&
          executions.map((execution) => (
            <button
              key={`${execution.bot_id}-${execution.task_id}`}
              type="button"
              onClick={() => onExecutionClick?.(execution)}
              className={cn(
                "app-card-row app-card-row--interactive block w-full text-left",
                selectedExecutionId === execution.task_id &&
                  "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.028)]"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: getStatusDotColor(execution.status) }} />
                      <span className="font-mono text-xs">{getStatusLabel(execution.status)}</span>
                    </span>
                    <span className="h-2 w-2 rounded-full" style={getSemanticStyle(traceSourceMeta[execution.trace_source].tone)} />
                    {showBot && (
                      <span className="inline-flex items-center gap-2 font-mono text-xs">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: getBotColor(execution.bot_id) }} />
                        {execution.bot_id}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                    <span className="font-mono">#{execution.task_id}</span>
                    <span className="h-1 w-1 rounded-full bg-[var(--border-strong)]" />
                    <span>{formatRelativeTime(execution.created_at)}</span>
                  </div>
                  <p className="line-clamp-2 text-sm leading-6 text-[var(--text-primary)]">
                    {execution.query_text || t("executions.table.noQueryRegistered")}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2.5 text-[12px]">
                <MobileStat label={t("executions.table.tools")} value={String(execution.tool_count)} mono />
                <MobileStat label={t("common.cost")} value={formatCost(execution.cost_usd)} mono />
                <MobileStat label={t("common.duration")} value={formatDuration(execution.duration_ms)} mono />
                <MobileStat
                  label={t("executions.table.warnings")}
                  value={execution.warning_count > 0 ? String(execution.warning_count) : "0"}
                  mono
                />
              </div>
            </button>
          ))}
        {executions.length === 0 && !loading && (
          <div className="empty-state">
            <Workflow className="empty-state-icon h-10 w-10" />
            <p className="empty-state-text">{t("executions.table.noResults")}</p>
          </div>
        )}
      </div>
    </>
  );
}

function MobileStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="border-b border-[rgba(255,255,255,0.06)] px-0 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className={cn("mt-1 text-[12px] text-[var(--text-secondary)]", mono && "font-mono tabular-nums")}>
        {mono ? truncateText(value, 22) : value}
      </p>
    </div>
  );
}
