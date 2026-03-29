"use client";

import { ArrowUpRight, CheckCircle2, Clock, ShieldCheck, XCircle } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { DLQEntry } from "@/lib/types";
import { getSemanticStyle, getSemanticTextStyle } from "@/lib/theme-semantic";
import { cn, formatDateTime, truncateText } from "@/lib/utils";

interface DLQTableProps {
  entries: DLQEntry[];
  loading?: boolean;
  onEntryClick?: (entry: DLQEntry) => void;
  selectedEntryId?: number | null;
}

function RetryIndicator({ entry }: { entry: DLQEntry }) {
  const { t } = useAppI18n();
  if (entry.retry_eligible === 1 && !entry.retried_at) {
    return (
      <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.01em]" style={getSemanticStyle("warning")}>
        <Clock className="h-3.5 w-3.5" />
        {t("dlq.table.canRetry")}
      </span>
    );
  }

  if (entry.retried_at) {
    return (
      <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.01em]" style={getSemanticStyle("success")}>
        <CheckCircle2 className="h-3.5 w-3.5" />
        {t("dlq.table.retried")}
      </span>
    );
  }

  return (
      <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.01em]" style={getSemanticStyle("danger")}>
        <XCircle className="h-3.5 w-3.5" />
      {t("dlq.table.noRetry")}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: 6 }).map((_, i) => (
        <td key={i}>
          <div className="skeleton skeleton-text" style={{ width: `${52 - i * 4}%` }} />
        </td>
      ))}
    </tr>
  );
}

export function DLQTable({
  entries,
  loading = false,
  onEntryClick,
  selectedEntryId,
}: DLQTableProps) {
  const { t } = useAppI18n();
  return (
    <>
      <div className="hidden md:block">
        <div className="table-shell overflow-x-auto">
          <table className="glass-table min-w-[980px]">
              <thead>
                <tr>
                  <th>{t("dlq.table.entry")}</th>
                  <th>{t("dlq.table.origin")}</th>
                  <th>{t("common.query")}</th>
                  <th>{t("dlq.table.error")}</th>
                  <th>{t("dlq.table.lastFailure")}</th>
                  <th className="text-right">{t("common.status")}</th>
                </tr>
              </thead>
              <tbody>
                {loading && Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
                {!loading &&
                  entries.map((entry) => (
                    <tr
                      key={entry.id}
                      onClick={() => onEntryClick?.(entry)}
                      className={cn(
                        "group transition-[background-color,border-color,box-shadow] duration-150",
                        selectedEntryId === entry.id && "bg-[var(--table-row-selected)]",
                        onEntryClick && "cursor-pointer"
                      )}
                    >
                      <td className="w-[124px]">
                        <div className="space-y-1">
                          <p className="font-mono text-xs text-foreground">DLQ #{entry.id}</p>
                          <p className="text-[10.5px] text-[var(--text-quaternary)]">
                            {entry.bot_id ?? t("dlq.table.noBot")}
                          </p>
                        </div>
                      </td>
                      <td className="w-[124px]">
                        <div className="space-y-1">
                          <p className="font-mono text-xs text-foreground">#{entry.task_id}</p>
                          <p className="text-[10.5px] text-[var(--text-quaternary)]">
                            {entry.model ?? t("dlq.table.modelUnknown")}
                          </p>
                        </div>
                      </td>
                      <td className="min-w-[280px]">
                        <p
                          className="line-clamp-2 text-[13px] leading-6 text-[var(--text-primary)] transition-colors group-hover:text-[var(--text-primary)]"
                          title={entry.query_text}
                        >
                          {truncateText(entry.query_text, 110)}
                        </p>
                      </td>
                      <td className="min-w-[280px]">
                        <div className="space-y-2">
                          <p className="line-clamp-2 text-[13px] leading-6" style={getSemanticTextStyle("danger", true)}>
                            {entry.error_message ? truncateText(entry.error_message, 110) : "\u2014"}
                          </p>
                          {entry.error_class && (
                            <span className="inline-flex rounded-lg border px-2.5 py-1 font-mono text-[10px]" style={getSemanticStyle("danger")}>
                              {entry.error_class}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="w-[176px]">
                        <div className="space-y-1">
                          <p className="text-xs text-[var(--text-secondary)]">{formatDateTime(entry.failed_at)}</p>
                          <p className="text-[10.5px] text-[var(--text-quaternary)]">
                            {entry.retried_at ? t("dlq.table.alreadyReprocessed") : t("dlq.table.waitingDecision")}
                          </p>
                        </div>
                      </td>
                      <td className="text-right">
                        <RetryIndicator entry={entry} />
                      </td>
                    </tr>
                  ))}
                {entries.length === 0 && !loading && (
                  <tr>
                    <td colSpan={6}>
                        <div className="empty-state">
                          <ShieldCheck className="empty-state-icon h-10 w-10" />
                        <p className="empty-state-text">{t("dlq.table.noFailures")}</p>
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
              <div className="skeleton skeleton-text w-24" />
              <div className="skeleton skeleton-heading w-full" />
              <div className="skeleton skeleton-text w-28" />
            </div>
          ))}
        {!loading &&
          entries.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => onEntryClick?.(entry)}
              className={cn(
                "app-card-row app-card-row--interactive block w-full text-left",
                selectedEntryId === entry.id &&
                  "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.028)]"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">DLQ #{entry.id}</span>
                    <RetryIndicator entry={entry} />
                  </div>
                  <p className="line-clamp-2 text-sm leading-6 text-[var(--text-primary)]">
                    {truncateText(entry.query_text, 90)}
                  </p>
                  <p className="line-clamp-2 text-[12px] leading-5" style={getSemanticTextStyle("danger", true)}>
                    {entry.error_message ? truncateText(entry.error_message, 90) : t("dlq.table.noErrorMessage")}
                  </p>
                </div>
                <ArrowUpRight className="mt-0.5 h-4 w-4 text-[var(--text-quaternary)]" />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2.5">
                <MobileDlqStat label={t("dlq.table.origin")} value={`#${entry.task_id}`} mono />
                <MobileDlqStat label={t("common.bot")} value={entry.bot_id ?? "—"} />
                <MobileDlqStat label={t("dlq.table.lastFailure")} value={formatDateTime(entry.failed_at)} />
              </div>
            </button>
          ))}
        {entries.length === 0 && !loading && (
          <div className="empty-state">
            <ShieldCheck className="empty-state-icon h-10 w-10" />
            <p className="empty-state-text">{t("dlq.table.noFailures")}</p>
          </div>
        )}
      </div>
    </>
  );
}

function MobileDlqStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">{label}</p>
      <p className={mono ? "mt-1 font-mono text-[12px] text-[var(--text-secondary)]" : "mt-1 text-[12px] text-[var(--text-secondary)]"}>
        {value}
      </p>
    </div>
  );
}
