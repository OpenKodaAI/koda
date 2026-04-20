"use client";

import { createPortal } from "react-dom";
import { X, Copy } from "lucide-react";
import type { Task } from "@/lib/types";
import { cn, formatCost, formatDuration, formatDateTime, formatRelativeTime, truncateText } from "@/lib/utils";
import {
  getSemanticIconStyle,
  getSemanticTextStyle,
} from "@/lib/theme-semantic";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { StatusPill } from "./status-pill";
import { SyntaxHighlight } from "../shared/syntax-highlight";
import { getAgentColor } from "@/lib/agent-constants";
import { DetailRow } from "../shared/detail-row";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface TaskDetailProps {
  task: (Task & { agentId?: string }) | null;
  onClose: () => void;
}

function computeDurationMs(startedAt: string | null, completedAt: string | null): number | null {
  if (!startedAt || !completedAt) return null;
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  return ms >= 0 ? ms : null;
}

function copyText(value: string | null | undefined) {
  if (!value) return;
  void navigator.clipboard?.writeText(value);
}

export function TaskDetail({ task, onClose }: TaskDetailProps) {
  const { t, tl } = useAppI18n();
  const presence = useAnimatedPresence(Boolean(task), { task }, { duration: 180 });
  const renderedTask = presence.renderedValue.task;
  const agentColor = renderedTask?.agentId ? getAgentColor(renderedTask.agentId) : null;

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender || !renderedTask) return null;

  if (typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className={cn(
          "app-overlay-backdrop",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-[70] w-full max-w-[720px] transition-opacity duration-150 ease-out",
          presence.isVisible
            ? "opacity-100"
            : "pointer-events-none opacity-0"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={t("tasks.detail.dialogTitle", { id: renderedTask.id })}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t("tasks.detail.close")}
          className="app-surface-close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="app-drawer-panel h-full overflow-y-auto p-5 lg:p-6">
          <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pr-14 sm:pr-16">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="app-card-row__eyebrow">{t("tasks.detail.taskEyebrow", { id: renderedTask.id })}</span>
                  <StatusPill status={renderedTask.status} />
                  {renderedTask.agentId && (
                    <span
                      className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[10px] font-semibold tracking-[0.08em]"
                      style={{
                        backgroundColor: agentColor
                          ? `color-mix(in srgb, ${agentColor} 18%, var(--surface-panel-soft))`
                          : "var(--surface-panel-soft)",
                        color: agentColor ?? "var(--text-secondary)",
                        borderColor: agentColor
                          ? `color-mix(in srgb, ${agentColor} 36%, var(--border-subtle))`
                          : "var(--border-subtle)",
                      }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: agentColor ?? "var(--text-secondary)" }} />
                      {renderedTask.agentId}
                    </span>
                  )}
                </div>
                <div>
                  <h2 className="text-[1.35rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
                    {renderedTask.query_text
                      ? truncateText(renderedTask.query_text, 96)
                      : t("tasks.detail.executionFallback", { id: renderedTask.id })}
                  </h2>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                  <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
                    {renderedTask.model ?? t("tasks.table.noModel")}
                  </span>
                  <span>{formatRelativeTime(renderedTask.created_at)}</span>
                  {renderedTask.session_id && (
                    <span className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-quaternary)]">
                      {t("tasks.table.session", { value: truncateText(renderedTask.session_id, 18) })}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <DrawerMetric label={t("common.cost")} value={formatCost(renderedTask.cost_usd)} mono />
              <DrawerMetric
                label={t("common.duration")}
                value={formatDuration(computeDurationMs(renderedTask.started_at, renderedTask.completed_at))}
                mono
              />
              <DrawerMetric label={t("common.attempts")} value={`${renderedTask.attempt}/${renderedTask.max_attempts}`} mono />
            </div>

            <div className="app-code-panel sm:p-5">
              <div className="app-code-panel__header">
                <span className="app-code-panel__title">{t("common.message")}</span>
                <button
                  onClick={() => copyText(renderedTask.query_text)}
                  className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
                  title={t("tasks.detail.copyQuery")}
                >
                  <Copy className="h-3.5 w-3.5" />
                  {t("common.copy")}
                </button>
              </div>
              <SyntaxHighlight className="app-code-panel__body p-4">
                {renderedTask.query_text ?? "\u2014"}
              </SyntaxHighlight>
            </div>

            <div className="space-y-3">
              <span className="app-card-row__eyebrow">
                {t("common.details")}
              </span>
              <div className="app-detail-grid sm:grid-cols-2">
                <DetailRow label={t("common.model")}>
                  <span className="font-mono">{renderedTask.model ?? "\u2014"}</span>
                </DetailRow>
                <DetailRow label={t("common.agent")}>
                  <span className="font-mono">{renderedTask.agentId ?? "\u2014"}</span>
                </DetailRow>
                <DetailRow label={t("common.user")}>
                  <span className="font-mono">{renderedTask.user_id}</span>
                </DetailRow>
                <DetailRow label={tl("Chat")}>
                  <span className="font-mono">{renderedTask.chat_id}</span>
                </DetailRow>
                <DetailRow label={t("common.workspaceDirectory")}>
                  <span className="break-all font-mono text-xs">{renderedTask.work_dir ?? "\u2014"}</span>
                </DetailRow>
                <DetailRow label={t("common.session")}>
                  <span className="break-all font-mono text-xs">{renderedTask.session_id ?? "\u2014"}</span>
                </DetailRow>
              </div>
            </div>

            <div className="space-y-3">
              <span className="app-card-row__eyebrow">
                {t("common.timing")}
              </span>
              <div className="app-detail-grid sm:grid-cols-2">
                <DetailRow label={t("common.created")}>
                  {formatDateTime(renderedTask.created_at)}
                </DetailRow>
                <DetailRow label={t("common.startedAt")}>
                  {formatDateTime(renderedTask.started_at)}
                </DetailRow>
                <DetailRow label={t("common.completedAt")}>
                  {formatDateTime(renderedTask.completed_at)}
                </DetailRow>
                <DetailRow label={t("common.totalTime")}>
                  <span className="font-mono">{formatDuration(computeDurationMs(renderedTask.started_at, renderedTask.completed_at))}</span>
                </DetailRow>
              </div>
            </div>

            {renderedTask.error_message && (
              <div className="app-note app-note--danger">
                <div className="mb-3 flex items-center justify-between gap-4">
                  <span className="app-card-row__eyebrow" style={getSemanticTextStyle("danger")}>
                    {t("tasks.detail.failure")}
                  </span>
                  <button
                    onClick={() => copyText(renderedTask.error_message)}
                    className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[11px] font-semibold transition-colors hover:opacity-90"
                    style={getSemanticIconStyle("danger")}
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {t("common.copy")}
                  </button>
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7" style={getSemanticTextStyle("danger")}>
                  {renderedTask.error_message}
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
    <div className="app-kpi-card">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className={cn("mt-2 text-sm text-[var(--text-primary)]", mono && "font-mono tabular-nums")}>
        {value}
      </p>
    </div>
  );
}
