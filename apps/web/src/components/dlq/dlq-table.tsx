"use client";

import { ArrowUpRight, CheckCircle2, Clock, ShieldCheck, XCircle } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { DLQEntry } from "@/lib/types";
import { cn, formatDateTime, formatRelativeTime, truncateText } from "@/lib/utils";

interface DLQTableProps {
  entries: DLQEntry[];
  loading?: boolean;
  onEntryClick?: (entry: DLQEntry) => void;
  selectedEntryId?: number | null;
}

interface RetryState {
  tone: StatusDotTone;
  label: string;
  icon: typeof Clock;
}

function resolveRetryState(entry: DLQEntry, t: ReturnType<typeof useAppI18n>["t"]): RetryState {
  if (entry.retried_at) {
    return {
      tone: "success",
      label: t("dlq.table.retried"),
      icon: CheckCircle2,
    };
  }
  if (entry.retry_eligible === 1) {
    return {
      tone: "warning",
      label: t("dlq.table.canRetry"),
      icon: Clock,
    };
  }
  return {
    tone: "danger",
    label: t("dlq.table.noRetry"),
    icon: XCircle,
  };
}

function RetryIndicator({ entry }: { entry: DLQEntry }) {
  const { t } = useAppI18n();
  const state = resolveRetryState(entry, t);
  return (
    <span className="inline-flex items-center gap-1.5 text-[0.75rem] text-[var(--text-secondary)]">
      <StatusDot tone={state.tone} />
      {state.label}
    </span>
  );
}

function SkeletonRow({ columns }: { columns: number }) {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="py-3 pr-4">
          <div
            className="h-3 rounded bg-[var(--panel-soft)]"
            style={{ width: `${52 - i * 4}%` }}
          />
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
  const thClass =
    "py-2.5 pr-4 text-left font-mono text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]";
  const thRightClass = `${thClass} text-right`;

  return (
    <>
      <div className="hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-[color:var(--divider-hair)]">
                <th className={thClass}>{t("dlq.table.entry")}</th>
                <th className={thClass}>{t("dlq.table.origin")}</th>
                <th className={thClass}>{t("common.query")}</th>
                <th className={thClass}>{t("dlq.table.error")}</th>
                <th className={thClass}>{t("dlq.table.lastFailure")}</th>
                <th className={thRightClass}>{t("common.status")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--divider-hair)]">
              {loading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonRow key={i} columns={6} />
                ))}
              {!loading &&
                entries.map((entry) => {
                  const isSelected = selectedEntryId === entry.id;
                  return (
                    <tr
                      key={entry.id}
                      onClick={() => onEntryClick?.(entry)}
                      className={cn(
                        "group transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        onEntryClick && "cursor-pointer",
                        isSelected
                          ? "bg-[var(--hover-tint)]"
                          : onEntryClick && "hover:bg-[var(--hover-tint)]",
                      )}
                    >
                      <td className="w-[140px] py-3 pr-4">
                        <p className="m-0 font-mono text-[0.75rem] text-[var(--text-primary)]">
                          DLQ #{entry.id}
                        </p>
                        <p className="m-0 text-[0.6875rem] text-[var(--text-quaternary)]">
                          {entry.bot_id ?? t("dlq.table.noAgent")}
                        </p>
                      </td>
                      <td className="w-[128px] py-3 pr-4">
                        <p className="m-0 font-mono text-[0.75rem] text-[var(--text-primary)]">
                          #{entry.task_id}
                        </p>
                        <p className="m-0 text-[0.6875rem] text-[var(--text-quaternary)]">
                          {entry.model ?? t("dlq.table.modelUnknown")}
                        </p>
                      </td>
                      <td className="min-w-[260px] py-3 pr-4">
                        <p
                          className="m-0 line-clamp-2 text-[0.8125rem] leading-[1.5] text-[var(--text-primary)]"
                          title={entry.query_text}
                        >
                          {truncateText(entry.query_text, 110)}
                        </p>
                      </td>
                      <td className="min-w-[260px] py-3 pr-4">
                        <p
                          className="m-0 line-clamp-2 text-[0.8125rem] leading-[1.5] text-[var(--tone-danger-text)]"
                          title={entry.error_message ?? undefined}
                        >
                          {entry.error_message ? truncateText(entry.error_message, 110) : "—"}
                        </p>
                        {entry.error_class ? (
                          <p className="m-0 mt-0.5 font-mono text-[0.6875rem] text-[var(--tone-danger-dot)]">
                            {entry.error_class}
                          </p>
                        ) : null}
                      </td>
                      <td className="w-[160px] py-3 pr-4">
                        <p
                          className="m-0 text-[0.75rem] text-[var(--text-secondary)]"
                          title={formatDateTime(entry.failed_at)}
                        >
                          {formatRelativeTime(entry.failed_at)}
                        </p>
                        <p className="m-0 text-[0.6875rem] text-[var(--text-quaternary)]">
                          {entry.retried_at
                            ? t("dlq.table.alreadyReprocessed")
                            : t("dlq.table.waitingDecision")}
                        </p>
                      </td>
                      <td className="py-3 text-right">
                        <RetryIndicator entry={entry} />
                      </td>
                    </tr>
                  );
                })}
              {entries.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="py-12">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <ShieldCheck
                        className="icon-lg text-[var(--text-quaternary)]"
                        strokeWidth={1.5}
                        aria-hidden
                      />
                      <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
                        {t("dlq.table.noFailures")}
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
            <div
              key={i}
              className="flex animate-pulse flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 last:border-b-0"
            >
              <div className="h-3 w-24 rounded bg-[var(--panel-soft)]" />
              <div className="h-3 w-full rounded bg-[var(--panel-soft)]" />
              <div className="h-3 w-2/3 rounded bg-[var(--panel-soft)]" />
            </div>
          ))}
        {!loading &&
          entries.map((entry) => {
            const isSelected = selectedEntryId === entry.id;
            return (
              <button
                key={entry.id}
                type="button"
                onClick={() => onEntryClick?.(entry)}
                className={cn(
                  "flex w-full flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 text-left transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] last:border-b-0",
                  isSelected
                    ? "bg-[var(--hover-tint)]"
                    : onEntryClick && "hover:bg-[var(--hover-tint)]",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2 text-[0.75rem]">
                      <span className="font-mono text-[var(--text-quaternary)]">
                        DLQ #{entry.id}
                      </span>
                      <span className="text-[var(--text-quaternary)]">·</span>
                      <span className="font-mono text-[var(--text-secondary)]">
                        #{entry.task_id}
                      </span>
                      <span className="text-[var(--text-quaternary)]">·</span>
                      <RetryIndicator entry={entry} />
                    </div>
                    <p className="m-0 line-clamp-2 text-[var(--font-size-sm)] leading-[1.5] text-[var(--text-primary)]">
                      {truncateText(entry.query_text, 110)}
                    </p>
                    <p className="m-0 line-clamp-2 text-[0.75rem] leading-[1.5] text-[var(--tone-danger-text)]">
                      {entry.error_message
                        ? truncateText(entry.error_message, 110)
                        : t("dlq.table.noErrorMessage")}
                    </p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                      {entry.bot_id ? (
                        <span>
                          agent: <span className="text-[var(--text-secondary)]">{entry.bot_id}</span>
                        </span>
                      ) : null}
                      <span>
                        failed:{" "}
                        <span className="text-[var(--text-secondary)]">
                          {formatRelativeTime(entry.failed_at)}
                        </span>
                      </span>
                    </div>
                  </div>
                  <ArrowUpRight
                    className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-quaternary)]"
                    strokeWidth={1.75}
                    aria-hidden
                  />
                </div>
              </button>
            );
          })}
        {entries.length === 0 && !loading && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <ShieldCheck
              className="icon-lg text-[var(--text-quaternary)]"
              strokeWidth={1.5}
              aria-hidden
            />
            <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
              {t("dlq.table.noFailures")}
            </p>
          </div>
        )}
      </div>
    </>
  );
}
