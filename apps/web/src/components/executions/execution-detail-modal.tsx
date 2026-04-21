"use client";

import { createPortal } from "react-dom";
import { Copy, X } from "lucide-react";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { getAgentColor } from "@/lib/agent-constants";
import {
  ExecutionDetailContent,
  copyExecutionValue,
  getExecutionDisplayDetail,
} from "./execution-detail-content";
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
  const { t, tl } = useAppI18n();
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
        className={cn(
          "app-overlay-backdrop transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div className="app-modal-frame z-[70] p-3 sm:p-5 lg:p-7">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={tl("Expanded execution {{id}}", {
            id: data.task_id,
          })}
          className={cn(
            "app-modal-panel relative flex h-[min(92vh,980px)] w-[min(92vw,1180px)] flex-col overflow-hidden transition-opacity duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
            presence.isVisible
              ? "opacity-100"
              : "pointer-events-none opacity-0"
          )}
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

          <div className="sticky top-0 z-10 border-b border-[rgba(255,255,255,0.07)] bg-[rgba(10,10,10,0.94)] px-6 py-4 pr-14 backdrop-blur-xl sm:px-7 sm:pr-16 lg:px-8">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="metric-label">{t("tasks.detail.executionFallback", { id: data.task_id })}</span>
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: fallbackAgentColor }} />
                  <span className="font-mono text-xs text-[var(--text-tertiary)]">{data.bot_id}</span>
                </div>
                <h2 className="text-[1.4rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)] sm:text-[1.6rem]">
                  {data.query_text ? truncateText(data.query_text, 110) : t("tasks.detail.executionFallback", { id: data.task_id })}
                </h2>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button type="button" onClick={() => copyExecutionValue(data.query_text ?? data.response_text ?? t("tasks.detail.executionFallback", { id: data.task_id }))}
                  className="button-shell button-shell--secondary button-shell--sm gap-2 px-3">
                  <Copy className="h-3.5 w-3.5" />
                  {t("common.copy")}
                </button>
              </div>
            </div>
          </div>

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
