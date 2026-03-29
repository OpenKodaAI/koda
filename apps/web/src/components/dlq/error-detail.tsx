"use client";

import { createPortal } from "react-dom";
import { X, CheckCircle2, XCircle, Clock, AlertTriangle, Copy } from "lucide-react";
import type { DLQEntry } from "@/lib/types";
import { cn, formatDateTime, truncateText } from "@/lib/utils";
import {
  getSemanticIconStyle,
  getSemanticStyle,
  getSemanticTextStyle,
} from "@/lib/theme-semantic";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { DetailRow } from "../shared/detail-row";
import { SyntaxHighlight } from "../shared/syntax-highlight";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ErrorDetailProps {
  entry: DLQEntry | null;
  onClose: () => void;
}

function RetryStatus({ entry }: { entry: DLQEntry }) {
  const { t } = useAppI18n();
  if (entry.retry_eligible === 1 && !entry.retried_at) {
    return (
      <span className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium" style={getSemanticStyle("warning")}>
        <Clock className="h-4 w-4" />
        {t("dlq.detail.retryNow")}
      </span>
    );
  }

  if (entry.retried_at) {
    return (
      <span className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium" style={getSemanticStyle("success")}>
        <CheckCircle2 className="h-4 w-4" />
        {t("dlq.detail.retriedAt", { value: formatDateTime(entry.retried_at) })}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium" style={getSemanticStyle("danger")}>
      <XCircle className="h-4 w-4" />
      {t("dlq.detail.noRetry")}
    </span>
  );
}

function MetadataViewer({ json }: { json: string }) {
  const { t } = useAppI18n();
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(json);
  } catch {
    return (
      <SyntaxHighlight lang="json" className="p-4">
        {json}
      </SyntaxHighlight>
    );
  }

  const entries = Object.entries(parsed);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] p-4">
        <span className="font-mono text-sm italic text-subtle">{t("dlq.detail.emptyMetadata")}</span>
      </div>
    );
  }

  return (
    <SyntaxHighlight lang="json" className="p-4">
      {JSON.stringify(parsed, null, 2)}
    </SyntaxHighlight>
  );
}

function copyText(value: string | null | undefined) {
  if (!value) return;
  void navigator.clipboard?.writeText(value);
}

export function ErrorDetail({ entry, onClose }: ErrorDetailProps) {
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
          "fixed inset-y-0 right-0 z-[70] w-full max-w-xl will-change-transform transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)]",
          presence.isVisible
            ? "translate-x-0 opacity-100"
            : "pointer-events-none translate-x-3 opacity-0"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={t("dlq.detail.dialogTitle", { id: renderedEntry.id })}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t("dlq.detail.close")}
          className="app-surface-close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="app-drawer-panel h-full overflow-y-auto p-5 lg:p-7">
          <div className="flex flex-col gap-6">
              <div className="flex items-start gap-4 pr-14 sm:pr-16">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="app-card-row__eyebrow">DLQ #{renderedEntry.id}</span>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">Task #{renderedEntry.task_id}</span>
                    {renderedEntry.bot_id && (
                      <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                        {renderedEntry.bot_id}
                      </span>
                    )}
                  </div>
                  <div>
                    <h2 className="text-[1.35rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
                      {renderedEntry.error_message
                        ? truncateText(renderedEntry.error_message, 92)
                        : t("dlq.detail.empty")}
                    </h2>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <DrawerMetric label={t("common.model")} value={truncateText(renderedEntry.model ?? "—", 18)} mono />
                <DrawerMetric label={t("common.attempts")} value={`${renderedEntry.attempt_count}`} mono />
                <DrawerMetric label={t("common.pod")} value={truncateText(renderedEntry.pod_name ?? "—", 18)} mono />
                <DrawerMetric label={t("common.bot")} value={renderedEntry.bot_id ?? "—"} mono />
              </div>

              <div className="app-code-panel">
                <div className="app-code-panel__header">
                  <span className="app-code-panel__title">{t("dlq.detail.originalQuery")}</span>
                  <button
                    onClick={() => copyText(renderedEntry.query_text)}
                    className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {t("common.copy")}
                  </button>
                </div>
                <SyntaxHighlight className="app-code-panel__body p-4">
                  {renderedEntry.query_text || "\u2014"}
                </SyntaxHighlight>
              </div>

              <div className="app-note app-note--danger" style={getSemanticStyle("danger")}>
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" style={getSemanticTextStyle("danger")} />
                    <span className="app-card-row__eyebrow" style={getSemanticTextStyle("danger")}>
                      {t("dlq.detail.failure")}
                    </span>
                  </div>
                  <button
                    onClick={() => copyText(renderedEntry.error_message)}
                    className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[11px] font-semibold transition-colors hover:opacity-90"
                    style={getSemanticIconStyle("danger")}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {t("common.copy")}
                    </button>
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7" style={getSemanticTextStyle("danger")}>
                  {renderedEntry.error_message ?? "\u2014"}
                </pre>
              </div>

              <div className="space-y-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  {t("dlq.detail.operationalContext")}
                </span>
                <div className="app-detail-grid sm:grid-cols-2">
                  <DetailRow label={t("dlq.detail.errorClass")}>
                    {renderedEntry.error_class ? (
                      <span className="inline-flex rounded-lg border px-2.5 py-1 font-mono text-xs" style={getSemanticStyle("danger")}>
                        {renderedEntry.error_class}
                      </span>
                    ) : (
                      <span className="text-subtle">&mdash;</span>
                    )}
                  </DetailRow>
                  <DetailRow label={t("dlq.detail.retryStatus")}>
                    <RetryStatus entry={renderedEntry} />
                  </DetailRow>
                  <DetailRow label={t("common.created")}>
                    {formatDateTime(renderedEntry.original_created_at)}
                  </DetailRow>
                  <DetailRow label={t("dlq.detail.failedAt")}>
                    {formatDateTime(renderedEntry.failed_at)}
                  </DetailRow>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <span className="app-card-row__eyebrow">
                    {t("dlq.detail.rawPayload")}
                  </span>
                  <button
                    onClick={() => copyText(renderedEntry.metadata_json)}
                    className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {t("dlq.detail.copyJson")}
                  </button>
                </div>
                <MetadataViewer json={renderedEntry.metadata_json} />
              </div>
            </div>
        </div>
      </div>
    </>,
    document.body
  );
}

function DrawerMetric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="app-kpi-card">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className={mono ? "mt-2 font-mono text-sm text-[var(--text-primary)]" : "mt-2 text-sm text-[var(--text-primary)]"}>
        {value}
      </p>
    </div>
  );
}
