"use client";

import { createPortal } from "react-dom";
import { Copy, X } from "lucide-react";
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
  copyExecutionValue,
  getExecutionDisplayDetail,
} from "./execution-detail-content";
import { ExecutionStatusPill } from "./execution-status-pill";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ExecutionDetailModalProps {
  execution: ExecutionSummary | null;
  detail: ExecutionDetail | null;
  loading?: boolean;
  error?: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function ExecutionDetailModal({
  execution,
  detail,
  loading = false,
  error,
  isOpen,
  onClose,
}: ExecutionDetailModalProps) {
  const { t } = useAppI18n();
  const presence = useAnimatedPresence(
    isOpen && Boolean(execution),
    { execution, detail, loading, error },
    { duration: 320 }
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
      <div className="app-modal-frame z-[70] p-3 sm:p-5 lg:p-7">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("generated.executions.expanded_execution_id_772264c3", {
            id: data.task_id,
          })}
          data-visible={presence.isVisible}
          className="app-modal-panel app-modal-anim relative flex h-[min(92vh,980px)] w-[min(92vw,1180px)] flex-col overflow-hidden"
          style={
            agentColor
              ? {
                  boxShadow: `0 36px 140px rgba(0,0,0,0.55), inset 0 1px 0 ${agentColor}12`,
                }
              : undefined
          }
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={t("common.close")}
          >
            <X className="h-4 w-4" />
          </button>

          <header className="sticky top-0 z-10 border-b border-[var(--border-subtle)] bg-[rgba(10,10,10,0.94)] px-6 py-5 pr-14 backdrop-blur-xl sm:px-7 sm:pr-16 lg:px-8 lg:py-6">
            <div className="flex items-start justify-between gap-4">
              {/* Hero */}
              <div className="flex min-w-0 flex-1 items-center gap-5">
                <AgentSigil
                  agentId={data.bot_id}
                  label={getAgentLabel(data.bot_id)}
                  color={fallbackAgentColor}
                  status={data.status}
                  size="lg"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h2 className="m-0 truncate text-[1.25rem] font-medium tracking-[-0.018em] text-[var(--text-primary)] sm:text-[1.4rem]">
                      {getAgentLabel(data.bot_id)}
                    </h2>
                    <ExecutionStatusPill
                      status={data.status}
                      label={t(`runtime.labels.${data.status}`, {
                        defaultValue: data.status,
                      })}
                      size="md"
                    />
                  </div>
                  <p className="m-0 mt-1 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                    #{data.task_id} · {data.bot_id}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    copyExecutionValue(
                      data.query_text ??
                        data.response_text ??
                        t("tasks.detail.executionFallback", {
                          id: data.task_id,
                        }),
                    )
                  }
                  className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
                >
                  <Copy className="h-3.5 w-3.5" />
                  {t("common.copy")}
                </button>
              </div>
            </div>

            {data.query_text ? (
              <p className="m-0 mt-4 line-clamp-3 text-[var(--font-size-sm)] leading-[1.55] text-[var(--text-secondary)] lg:text-[0.9375rem]">
                {data.query_text}
              </p>
            ) : null}
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 sm:px-7 lg:px-8 lg:py-7">
            <ExecutionDetailContent
              data={data}
              detailLoaded={Boolean(matchedDetail)}
              loading={renderedLoading}
              error={renderedError}
              variant="expanded"
            />
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
