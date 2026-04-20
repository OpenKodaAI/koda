"use client";

import { createPortal } from "react-dom";
import { Expand, X } from "lucide-react";
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
  getExecutionDisplayDetail,
} from "./execution-detail-content";
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
        className={cn(
          "app-overlay-backdrop",
          presence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-[70] w-full sm:w-[min(100vw,720px)] xl:w-[620px] 2xl:w-[680px] transition-opacity duration-150 ease-out",
          presence.isVisible
            ? "opacity-100"
            : "pointer-events-none opacity-0"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={data ? `${t("common.details")} · ${t("tasks.detail.executionFallback", { id: data.task_id })}` : t("common.details")}
        >
        <div className="app-drawer-panel relative ml-auto flex h-full w-full flex-col overflow-hidden">
          <div className="border-b border-[var(--border-subtle)] px-5 py-4 lg:px-6">
            {/* Action buttons row */}
            <div className="flex items-center justify-end gap-1 mb-3">
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

            {/* Title */}
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="metric-label">{t("tasks.detail.executionFallback", { id: data.task_id })}</span>
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: fallbackAgentColor }} />
                <span className="font-mono text-xs text-[var(--text-tertiary)]">{data.bot_id}</span>
              </div>
              <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {data.query_text ? truncateText(data.query_text, 88) : t("tasks.detail.executionFallback", { id: data.task_id })}
              </h2>
            </div>
          </div>

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
