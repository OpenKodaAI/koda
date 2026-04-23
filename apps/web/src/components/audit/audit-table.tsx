"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import type { AuditEntry } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
  truncateText,
} from "@/lib/utils";
import { getSemanticStyle, type SemanticTone } from "@/lib/theme-semantic";
import { ScrollText, ArrowUpRight } from "lucide-react";

interface AuditTableProps {
  entries: AuditEntry[];
  loading?: boolean;
  onEntryClick?: (entry: AuditEntry) => void;
  selectedEntryId?: number | null;
}

function getEventTone(eventType: string): SemanticTone {
  const lower = eventType.toLowerCase();
  if (lower.includes("task")) return "info";
  if (lower.includes("error")) return "danger";
  if (lower.includes("cost")) return "warning";
  return "neutral";
}

function getDetailsObject(entry: AuditEntry): Record<string, unknown> {
  if (entry.details && Object.keys(entry.details).length > 0) {
    return entry.details;
  }

  try {
    const parsed = JSON.parse(entry.details_json);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function getDetailsPreview(entry: AuditEntry, t: (key: string, options?: Record<string, unknown>) => string): string {
  const details = getDetailsObject(entry);
  const parts: string[] = [];

  if (typeof details.tool === "string") {
    parts.push(t("audit.table.tool", { value: details.tool }));
  }
  if (typeof details.model === "string") {
    parts.push(t("audit.table.model", { value: details.model }));
  }
  if (typeof details.success === "boolean") {
    parts.push(details.success ? t("audit.table.success") : t("audit.table.failure"));
  }
  if (typeof details.attempt === "number") {
    parts.push(t("audit.table.attempt", { value: details.attempt }));
  }

  if (parts.length > 0) {
    return parts.join(" • ");
  }

  const raw =
    entry.details_json && entry.details_json !== "{}" ? entry.details_json : "";

  if (!raw) return t("audit.table.noDetails");

  return truncateText(raw.replace(/[{}"]/g, "").replace(/,/g, " • "), 110);
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <td key={i}>
          <div className="skeleton skeleton-text" style={{ width: `${55 - i * 5}%` }} />
        </td>
      ))}
    </tr>
  );
}

export function AuditTable({
  entries,
  loading = false,
  onEntryClick,
  selectedEntryId,
}: AuditTableProps) {
  const { t } = useAppI18n();
  return (
    <>
      <div className="hidden md:block">
        <div className="table-shell overflow-x-auto">
          <table className="glass-table min-w-full">
            <thead>
              <tr>
                <th>{t("audit.table.dateTime")}</th>
                <th>{t("audit.table.event")}</th>
                <th>{t("audit.table.context")}</th>
                <th className="text-right">{t("common.cost")}</th>
                <th className="text-right">{t("common.duration")}</th>
              </tr>
            </thead>
            <tbody>
              {loading && Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
              {!loading &&
                entries.map((entry) => {
                  const isSelected = selectedEntryId === entry.id;

                  return (
                    <tr
                      key={entry.id}
                    onClick={() => onEntryClick?.(entry)}
                    className={cn(
                      "group transition-[background-color,border-color,box-shadow] duration-150",
                      isSelected && "bg-[var(--surface-tint)]",
                      onEntryClick && "cursor-pointer"
                    )}
                  >
                      <td className="w-[176px]">
                        <div className="space-y-1">
                          <p className="text-xs text-[var(--text-secondary)]">
                            {formatRelativeTime(entry.timestamp)}
                          </p>
                          <p className="text-[11px] text-[var(--text-quaternary)]">
                            {formatDateTime(entry.timestamp)}
                          </p>
                          <p className="font-mono text-[11px] text-[var(--text-quaternary)]">
                            {t("audit.table.record", { id: entry.id })}
                          </p>
                        </div>
                      </td>
                      <td className="w-[200px]">
                        <span
                          className="inline-flex rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.02em]"
                          style={getSemanticStyle(getEventTone(entry.event_type))}
                        >
                          {entry.event_type}
                        </span>
                      </td>
                      <td className="min-w-[360px]">
                        <div className="space-y-1.5">
                          <p
                            className="text-sm leading-6 text-[var(--text-primary)] transition-colors group-hover:text-[var(--text-primary)]"
                            title={getDetailsPreview(entry, t)}
                          >
                            {getDetailsPreview(entry, t)}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                            <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-2.5 py-1">
                              {entry.bot_id ?? t("common.noAgent")}
                            </span>
                            <span>{t("audit.table.task", { value: entry.task_id != null ? `#${entry.task_id}` : "—" })}</span>
                            {entry.trace_id && (
                              <span className="font-mono text-[10px] text-[var(--text-quaternary)]">
                                {t("audit.table.trace", { value: truncateText(entry.trace_id, 16) })}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="text-right">
                        <p className="font-mono text-xs tabular-nums text-[var(--text-primary)]">
                          {formatCost(entry.cost_usd)}
                        </p>
                      </td>
                      <td className="text-right">
                        <p className="font-mono text-xs tabular-nums text-[var(--text-secondary)]">
                          {formatDuration(entry.duration_ms)}
                        </p>
                      </td>
                    </tr>
                  );
                })}
              {entries.length === 0 && !loading && (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-state">
                      <ScrollText className="empty-state-icon h-10 w-10" />
                      <p className="empty-state-text">{t("audit.table.noEntries")}</p>
                      <p className="empty-state-subtext">
                        {t("audit.table.noEntriesDescription")}
                      </p>
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
              <div className="skeleton skeleton-text w-20" />
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
                  <span
                    className="inline-flex rounded-lg border px-2.5 py-1 text-[11px] font-semibold tracking-[0.02em]"
                    style={getSemanticStyle(getEventTone(entry.event_type))}
                  >
                    {entry.event_type}
                  </span>
                  <p className="text-sm leading-6 text-[var(--text-primary)]">
                    {truncateText(getDetailsPreview(entry, t), 100)}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                    <span>{entry.bot_id ?? t("common.noAgent")}</span>
                    <span className="h-1 w-1 rounded-full bg-[var(--border-strong)]" />
                    <span>{formatRelativeTime(entry.timestamp)}</span>
                  </div>
                </div>
                <ArrowUpRight className="mt-0.5 h-4 w-4 text-[var(--text-quaternary)]" />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                <MobileAuditStat label={t("common.agent")} value={entry.bot_id ?? "—"} />
                <MobileAuditStat label={t("common.cost")} value={formatCost(entry.cost_usd)} mono />
                <MobileAuditStat label={t("common.duration")} value={formatDuration(entry.duration_ms)} mono />
              </div>
            </button>
          ))}
        {entries.length === 0 && !loading && (
          <div className="empty-state">
            <ScrollText className="empty-state-icon h-10 w-10" />
            <p className="empty-state-text">{t("audit.table.noEntries")}</p>
            <p className="empty-state-subtext">
              {t("audit.table.noEntriesMobileDescription")}
            </p>
          </div>
        )}
      </div>
    </>
  );
}

function MobileAuditStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-3 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">{label}</p>
      <p className={cn("mt-1 text-[12px] text-[var(--text-secondary)]", mono && "font-mono tabular-nums")}>
        {value}
      </p>
    </div>
  );
}
