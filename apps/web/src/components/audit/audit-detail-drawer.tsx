"use client";

import { createPortal } from "react-dom";
import { X, Copy, ScrollText } from "lucide-react";
import type { AuditEntry } from "@/lib/types";
import { cn, formatCost, formatDateTime, formatDuration, truncateText } from "@/lib/utils";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { DetailsViewer } from "./details-viewer";
import { DetailRow } from "../shared/detail-row";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface AuditDetailDrawerProps {
  entry: AuditEntry | null;
  onClose: () => void;
}

function copyText(value: string | null | undefined) {
  if (!value) return;
  void navigator.clipboard?.writeText(value);
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

export function AuditDetailDrawer({ entry, onClose }: AuditDetailDrawerProps) {
  const { t } = useAppI18n();
  const presence = useAnimatedPresence(Boolean(entry), { entry }, { duration: 300 });
  const renderedEntry = presence.renderedValue.entry;

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender || !renderedEntry) {
    return null;
  }

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className={cn(
          "app-overlay-backdrop transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-[70] w-full max-w-[720px] will-change-transform transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)]",
          presence.isVisible
            ? "translate-x-0 opacity-100"
            : "pointer-events-none translate-x-3 opacity-0"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={t("audit.detail.dialogTitle", { id: renderedEntry.id })}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t("audit.detail.close")}
          className="app-surface-close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="app-drawer-panel h-full overflow-y-auto p-5 lg:p-6">
          <div className="flex flex-col gap-5">
              <div className="flex items-start gap-4 pr-14 sm:pr-16">
                <div className="space-y-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">#{renderedEntry.id}</span>
                    <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                      {renderedEntry.event_type}
                    </span>
                  </div>
                  <div>
                    <h2 className="text-[1.55rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                      {t("audit.detail.eventTitle", { id: renderedEntry.id })}
                    </h2>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <DrawerMetric label={t("common.bot")} value={renderedEntry.bot_id ?? "—"} mono />
                <DrawerMetric label={t("common.task")} value={renderedEntry.task_id != null ? `#${renderedEntry.task_id}` : "—"} mono />
                <DrawerMetric label={t("common.cost")} value={formatCost(renderedEntry.cost_usd)} mono />
                <DrawerMetric label={t("common.duration")} value={formatDuration(renderedEntry.duration_ms)} mono />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <DetailRow label={t("audit.detail.eventDate")}>{formatDateTime(renderedEntry.timestamp)}</DetailRow>
                <DetailRow label={t("common.pod")}>
                  <span className="font-mono">{renderedEntry.pod_name ?? "—"}</span>
                </DetailRow>
                <DetailRow label={t("Trace ID", { defaultValue: "Trace ID" })}>
                  <span className="break-all font-mono text-xs">{renderedEntry.trace_id ?? "—"}</span>
                </DetailRow>
                <DetailRow label={t("common.user")}>
                  <span className="font-mono">{renderedEntry.user_id ?? "—"}</span>
                </DetailRow>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <ScrollText className="empty-state-icon h-10 w-10" />
                    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {t("common.payload")}
                    </span>
                  </div>
                  <button
                    onClick={() => copyText(renderedEntry.details_json)}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {t("audit.detail.copyJson")}
                  </button>
                </div>
                <DetailsViewer data={getDetailsObject(renderedEntry)} />
              </div>

              {renderedEntry.trace_id && (
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] sm:p-5">
                  <div className="mb-3 flex items-center justify-between gap-4">
                      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {t("audit.detail.traceability")}
                      </span>
                    <button
                      onClick={() => copyText(renderedEntry.trace_id)}
                      className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {t("common.copy")}
                    </button>
                  </div>
                  <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7 text-[var(--text-secondary)]">
                    {truncateText(renderedEntry.trace_id, 999)}
                  </pre>
                </div>
              )}
            </div>
        </div>
      </div>
    </>,
    document.body
  );
}

function DrawerMetric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className={cn("mt-2 text-sm text-[var(--text-primary)]", mono && "font-mono tabular-nums")}>
        {value}
      </p>
    </div>
  );
}
