"use client";

import { createPortal } from "react-dom";
import { Expand, X } from "lucide-react";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/types";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import {
  ExecutionDetailContent,
  getExecutionDisplayDetail,
} from "./execution-detail-content";
import { ExecutionStatusPill } from "./execution-status-pill";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ExecutionDetailDrawerProps {
  execution: ExecutionSummary | null;
  detail: ExecutionDetail | null;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  onExpand?: () => void;
  modalOpen?: boolean;
}

export function ExecutionDetailDrawer({
  execution,
  detail,
  loading = false,
  error,
  onClose,
  onExpand,
  modalOpen = false,
}: ExecutionDetailDrawerProps) {
  const { t } = useAppI18n();
  const isOpen = Boolean(execution) && !modalOpen;
  const presence = useAnimatedPresence(
    isOpen,
    { execution, detail, loading, error },
    { duration: 180 }
  );
  const renderedExecution = presence.renderedValue.execution;
  const renderedDetail = presence.renderedValue.detail;
  const renderedLoading = presence.isVisible ? loading : presence.renderedValue.loading;
  const renderedError = presence.isVisible ? error : presence.renderedValue.error;
  const matchedDetail =
    renderedDetail && renderedExecution && renderedDetail.task_id === renderedExecution.task_id
      ? renderedDetail
      : null;
  const data = getExecutionDisplayDetail(renderedExecution, matchedDetail);
  const agentColor = data ? getAgentColor(data.bot_id) : null;
  const fallbackAgentColor = agentColor ?? "#A7ADB4";

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  if (!presence.shouldRender || !renderedExecution || !data) {
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
        className="app-drawer-anim-right fixed inset-y-0 right-0 z-[70] w-full sm:w-[min(100vw,760px)] 2xl:w-[780px]"
        data-visible={presence.isVisible}
        role="dialog"
        aria-modal="true"
        aria-label={data ? `${t("common.details")} · ${t("tasks.detail.executionFallback", { id: data.task_id })}` : t("common.details")}
        >
        <div className="app-drawer-panel relative ml-auto flex h-full w-full flex-col overflow-hidden">
          <header className="border-b border-[var(--border-subtle)] px-5 pb-5 pt-4 lg:px-6">
            {/* Action buttons row */}
            <div className="mb-4 flex items-center justify-end gap-1">
              {onExpand && (
                <button
                  type="button"
                  onClick={onExpand}
                  aria-label={t("common.expand")}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-quaternary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                >
                  <Expand className="h-4 w-4" />
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                aria-label={t("common.close")}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-quaternary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Hero — orb + agent identity + status */}
            <div className="flex items-center gap-4">
              <AgentSigil
                agentId={data.bot_id}
                label={getAgentLabel(data.bot_id)}
                color={fallbackAgentColor}
                status={data.status}
                size="md"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="m-0 truncate text-[1.0625rem] font-medium tracking-[-0.014em] text-[var(--text-primary)]">
                    {getAgentLabel(data.bot_id)}
                  </h2>
                  <ExecutionStatusPill
                    status={data.status}
                    label={t(`runtime.labels.${data.status}`, {
                      defaultValue: data.status,
                    })}
                  />
                </div>
                <p className="m-0 mt-0.5 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                  #{data.task_id} · {data.bot_id}
                </p>
              </div>
            </div>

            {/* Query — the action */}
            {data.query_text ? (
              <p className="m-0 mt-4 line-clamp-3 break-words text-[var(--font-size-sm)] leading-[1.55] text-[var(--text-secondary)]">
                {data.query_text}
              </p>
            ) : null}
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 lg:px-6 lg:py-6">
            <ExecutionDetailContent
              data={data}
              detailLoaded={Boolean(matchedDetail)}
              loading={renderedLoading}
              error={renderedError}
              variant="drawer"
            />
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
