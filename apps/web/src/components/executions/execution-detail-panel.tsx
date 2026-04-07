"use client";

import { Expand, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { translate } from "@/lib/i18n";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/types";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";
import { getBotColor } from "@/lib/bot-constants";
import { getSemanticStyle } from "@/lib/theme-semantic";
import { StatusPill } from "../tasks/status-pill";
import {
  EXECUTION_TRACE_SOURCE_META,
  ExecutionDetailContent,
  getExecutionDisplayDetail,
} from "./execution-detail-content";

interface ExecutionDetailPanelProps {
  execution: ExecutionSummary | null;
  detail: ExecutionDetail | null;
  loading?: boolean;
  error?: string | null;
  isOpen: boolean;
  onClear: () => void;
  onExpand?: () => void;
}

export function ExecutionDetailPanel({
  execution,
  detail,
  loading = false,
  error,
  isOpen,
  onClear,
  onExpand,
}: ExecutionDetailPanelProps) {
  const { t } = useAppI18n();
  const matchedDetail =
    detail && execution && detail.task_id === execution.task_id ? detail : null;
  const data = getExecutionDisplayDetail(execution, matchedDetail);
  if (!execution || !data) {
    return null;
  }

  const botColor = getBotColor(data.bot_id);
  const traceMeta = EXECUTION_TRACE_SOURCE_META[data.trace_source];

  return (
    <div className="hidden h-[calc(100vh-4.5rem)] overflow-hidden xl:block">
      <aside
        className={cn(
          "glass-card sticky top-6 relative flex h-[calc(100vh-4.5rem)] w-[488px] flex-col overflow-hidden transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          isOpen
            ? "opacity-100"
            : "pointer-events-none opacity-0"
        )}
      >
        <button
          type="button"
          onClick={onClear}
          className="app-surface-close"
          aria-label={t("common.close")}
        >
          <X className="h-4 w-4" />
        </button>

        <div
          className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14 sm:pr-16"
          style={{ boxShadow: `inset 0 1px 0 ${botColor}12` }}
        >
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip">{t("tasks.detail.executionFallback", { id: data.task_id })}</span>
                  <StatusPill status={data.status} />
                  <span
                    className="inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-semibold tracking-[0.04em]"
                    style={getSemanticStyle(traceMeta.tone)}
                  >
                    {translate(traceMeta.labelKey)}
                  </span>
                </div>
                <h2 className="text-[1.35rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
                  {t("tasks.detail.executionFallback", { id: data.task_id })}
                </h2>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                {onExpand && (
                  <button
                    type="button"
                    onClick={onExpand}
                    className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
                  >
                    <Expand className="h-3.5 w-3.5" />
                    {t("common.open")}
                  </button>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
              <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                {data.model ?? t("tasks.table.noModel")}
              </span>
              {data.session_id && (
                <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-quaternary)]">
                  {t("tasks.table.session", { value: truncateText(data.session_id, 18) })}
                </span>
              )}
              <span>{formatRelativeTime(data.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <ExecutionDetailContent
            data={data}
            detailLoaded={Boolean(matchedDetail)}
            loading={loading}
            error={error}
            variant="panel"
          />
        </div>
      </aside>
    </div>
  );
}
