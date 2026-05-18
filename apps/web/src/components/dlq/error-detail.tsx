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
  const baseClass = "inline-flex min-h-7 items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium";
  if (entry.retry_eligible === 1 && !entry.retried_at) {
    return (
      <span className={baseClass} style={getSemanticStyle("warning")}>
        <Clock className="h-3.5 w-3.5" />
        {t("dlq.detail.retryNow")}
      </span>
    );
  }

  if (entry.retried_at) {
    return (
      <span className={baseClass} style={getSemanticStyle("success")}>
        <CheckCircle2 className="h-3.5 w-3.5" />
        {t("dlq.detail.retriedAt", { value: formatDateTime(entry.retried_at) })}
      </span>
    );
  }

  return (
    <span className={baseClass} style={getSemanticStyle("danger")}>
      <XCircle className="h-3.5 w-3.5" />
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
      <SyntaxHighlight lang="json" className="max-h-[220px] overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] p-3 text-xs leading-5">
        {json}
      </SyntaxHighlight>
    );
  }

  const entries = Object.entries(parsed);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] p-4">
        <span className="font-mono text-sm italic text-subtle">{t("dlq.detail.emptyMetadata")}</span>
      </div>
    );
  }

  return (
    <SyntaxHighlight lang="json" className="max-h-[220px] overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] p-3 text-xs leading-5">
      {JSON.stringify(parsed, null, 2)}
    </SyntaxHighlight>
  );
}

function copyText(value: string | null | undefined) {
  if (!value) return;
  void navigator.clipboard?.writeText(value);
}

function CopyAction({
  label,
  onClick,
  tone,
}: {
  label: string;
  onClick: () => void;
  tone?: "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="button-shell button-shell--secondary button-shell--sm h-8 min-h-8 gap-1.5 px-2.5 text-xs"
      style={tone === "danger" ? getSemanticIconStyle("danger") : undefined}
    >
      <Copy className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

export function ErrorDetail({ entry, onClose }: ErrorDetailProps) {
  const { t } = useAppI18n();
  const presence = useAnimatedPresence(Boolean(entry), { entry }, { duration: 180 });
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
        className="app-overlay-backdrop app-overlay-anim"
        data-visible={presence.isVisible}
        onClick={onClose}
      />

      <div
        className="app-drawer-anim-right fixed inset-y-0 right-0 z-[70] w-full max-w-xl"
        data-visible={presence.isVisible}
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

        <div className="app-drawer-panel h-full !overflow-y-auto p-4 lg:p-5">
          <div className="flex flex-col gap-4">
              <div className="flex items-start gap-3 pr-12 sm:pr-14">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="app-card-row__eyebrow">DLQ #{renderedEntry.id}</span>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">Task #{renderedEntry.task_id}</span>
                    {renderedEntry.bot_id && (
                      <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                        {renderedEntry.bot_id}
                      </span>
                    )}
                  </div>
                  <div>
                    <h2 className="text-[1.08rem] font-semibold leading-6 tracking-[-0.035em] text-[var(--text-primary)] sm:text-[1.15rem]">
                      {renderedEntry.error_message
                        ? truncateText(renderedEntry.error_message, 110)
                        : t("dlq.detail.empty")}
                    </h2>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
                <DrawerMetric label={t("common.model")} value={truncateText(renderedEntry.model ?? "—", 18)} mono />
                <DrawerMetric label={t("common.attempts")} value={`${renderedEntry.attempt_count}`} mono />
                <DrawerMetric label={t("common.pod")} value={truncateText(renderedEntry.pod_name ?? "—", 18)} mono />
                <DrawerMetric label={t("common.agent")} value={renderedEntry.bot_id ?? "—"} mono />
              </div>

              <div className="app-code-panel p-3">
                <div className="app-code-panel__header">
                  <span className="app-code-panel__title">{t("dlq.detail.originalQuery")}</span>
                  <CopyAction
                    label={t("common.copy")}
                    onClick={() => copyText(renderedEntry.query_text)}
                  />
                </div>
                <SyntaxHighlight className="app-code-panel__body max-h-32 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] p-3 text-xs leading-6">
                  {renderedEntry.query_text || "\u2014"}
                </SyntaxHighlight>
              </div>

              <div className="app-note app-note--danger p-3" style={getSemanticStyle("danger")}>
                <div className="mb-2.5 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" style={getSemanticTextStyle("danger")} />
                    <span className="app-card-row__eyebrow" style={getSemanticTextStyle("danger")}>
                      {t("dlq.detail.failure")}
                    </span>
                  </div>
                  <CopyAction
                    label={t("common.copy")}
                    onClick={() => copyText(renderedEntry.error_message)}
                    tone="danger"
                  />
                </div>
                <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[color:var(--tone-danger-border)] bg-[rgba(0,0,0,0.08)] p-3 font-mono text-xs leading-6" style={getSemanticTextStyle("danger")}>
                  {renderedEntry.error_message ?? "\u2014"}
                </pre>
              </div>

              <div className="space-y-2.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                  {t("dlq.detail.operationalContext")}
                </span>
                <div className="app-detail-grid gap-2 sm:grid-cols-2">
                  <DetailRow
                    label={t("dlq.detail.errorClass")}
                    className="px-3 py-2.5 sm:py-3"
                    valueClassName="mt-1 text-xs leading-5"
                  >
                    {renderedEntry.error_class ? (
                      <span className="inline-flex rounded-md border px-2 py-0.5 font-mono text-xs" style={getSemanticStyle("danger")}>
                        {renderedEntry.error_class}
                      </span>
                    ) : (
                      <span className="text-subtle">&mdash;</span>
                    )}
                  </DetailRow>
                  <DetailRow
                    label={t("dlq.detail.retryStatus")}
                    className="px-3 py-2.5 sm:py-3"
                    valueClassName="mt-1 text-xs leading-5"
                  >
                    <RetryStatus entry={renderedEntry} />
                  </DetailRow>
                  <DetailRow
                    label={t("common.created")}
                    className="px-3 py-2.5 sm:py-3"
                    valueClassName="mt-1 font-mono text-xs leading-5"
                  >
                    {formatDateTime(renderedEntry.original_created_at)}
                  </DetailRow>
                  <DetailRow
                    label={t("dlq.detail.failedAt")}
                    className="px-3 py-2.5 sm:py-3"
                    valueClassName="mt-1 font-mono text-xs leading-5"
                  >
                    {formatDateTime(renderedEntry.failed_at)}
                  </DetailRow>
                </div>
              </div>

              <div className="space-y-2.5">
                <div className="flex items-center justify-between gap-4">
                  <span className="app-card-row__eyebrow">
                    {t("dlq.detail.rawPayload")}
                  </span>
                  <CopyAction
                    label={t("dlq.detail.copyJson")}
                    onClick={() => copyText(renderedEntry.metadata_json)}
                  />
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
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3 py-2.5">
      <p className="truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className={cn("mt-1 truncate text-[13px] leading-5 text-[var(--text-primary)]", mono && "font-mono")}>
        {value}
      </p>
    </div>
  );
}
