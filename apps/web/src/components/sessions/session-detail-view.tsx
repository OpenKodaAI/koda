"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { MessageSquareText, TimerReset, X } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import type { ExecutionSummary, SessionDetail, SessionMessage } from "@/lib/types";
import {
  cn,
  formatCost,
  formatDuration,
  formatRelativeTime,
} from "@/lib/utils";

interface SessionDetailViewProps {
  detail: SessionDetail | null;
  loading?: boolean;
  error?: string | null;
  onClose?: () => void;
  className?: string;
  variant?: "default" | "immersive";
  showSummaryCard?: boolean;
  footer?: ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
  contentWidthClassName?: string;
  bodyClassName?: string;
}

function getPluralLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  keyBase: string,
  count: number,
) {
  return t(`${keyBase}_${count === 1 ? "one" : "other"}`, { count });
}

function SessionExecutionInline({
  execution,
}: {
  execution: ExecutionSummary;
}) {
  const { t } = useAppI18n();
  const label =
    execution.status === "running"
      ? t("sessions.detail.runningExecution")
      : execution.status === "failed"
        ? t("sessions.detail.failedExecution")
        : t("sessions.detail.executionLabel", {
            defaultValue: "Execution #{{id}}",
            id: execution.task_id,
          });

  return (
    <div className="mt-3 border-l border-[var(--border-strong)] pl-3 text-[11px] text-[var(--text-tertiary)]">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 leading-5">
        <span className="inline-flex items-center gap-2">
          <StatusIndicator status={execution.status} className="mt-0.5" />
          <span className="font-medium text-[var(--text-secondary)]">{label}</span>
        </span>
        <span>•</span>
        <span>{execution.model}</span>
        {execution.duration_ms != null ? (
          <>
            <span>•</span>
            <span>{formatDuration(execution.duration_ms)}</span>
          </>
        ) : null}
        {execution.tool_count > 0 ? (
          <>
            <span>•</span>
            <span>
              {t("sessions.detail.toolsCount", {
                defaultValue: "{{count}} tools",
                count: execution.tool_count,
              })}
            </span>
          </>
        ) : null}
        <span>•</span>
        <span>{formatCost(execution.cost_usd)}</span>
      </div>
    </div>
  );
}

function SessionMessageBubble({
  message,
  animate,
  botId,
  variant = "default",
}: {
  message: SessionMessage;
  animate?: boolean;
  botId: string;
  variant?: "default" | "immersive";
}) {
  const isAssistant = message.role === "assistant";
  const botLabel = getBotLabel(botId);
  const botColor = getBotColor(botId);
  const isImmersive = variant === "immersive";
  const { t } = useAppI18n();

  return (
    <div
      className={cn(
        "flex w-full",
        isAssistant ? "justify-start pr-10 sm:pr-14" : "justify-end pl-10 sm:pl-14",
        animate && "animate-in"
      )}
    >
      <div className={cn("max-w-[min(100%,43rem)]", !isAssistant && "text-right")}>
        {isAssistant ? (
          <div className="mb-2 flex items-center gap-2.5 pl-1">
            <BotAgentGlyph
              botId={botId}
              color={botColor}
              variant="list"
              className="h-8 w-8 shrink-0"
            />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
                {botLabel}
              </p>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-[var(--text-tertiary)]">
                {message.timestamp ? <span>{formatRelativeTime(message.timestamp)}</span> : null}
                {message.error ? (
                  <>
                    <span>•</span>
                    <span className="text-[var(--tone-danger-dot)]">{t("sessions.detail.error")}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="mb-1.5 pr-1 text-[10.5px] text-[var(--text-tertiary)]">
            {t("sessions.detail.you")}
            {message.timestamp ? ` • ${formatRelativeTime(message.timestamp)}` : ""}
          </div>
        )}

        <div
          className={cn(
            "rounded-[1.1rem] border px-4 py-3.5 text-left",
            isImmersive
              ? isAssistant
                ? "border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.026)] shadow-[0_18px_48px_rgba(0,0,0,0.18)]"
                : "border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.055)] shadow-[0_18px_48px_rgba(0,0,0,0.22)]"
              : isAssistant
                ? "border-[rgba(255,255,255,0.04)] bg-[rgba(255,255,255,0.014)]"
                : "border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.03)]"
          )}
        >
          <SessionRichText
            content={message.text}
            variant={isAssistant ? "assistant" : "user"}
          />

          {isAssistant && message.linked_execution ? (
            <SessionExecutionInline execution={message.linked_execution} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function SessionDetailView({
  detail,
  loading = false,
  error,
  onClose,
  className,
  variant = "default",
  showSummaryCard = true,
  footer,
  emptyTitle,
  emptyDescription,
  contentWidthClassName,
  bodyClassName,
}: SessionDetailViewProps) {
  const { t } = useAppI18n();
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const seenMessageIdsRef = useRef<Set<string>>(new Set());
  const animationTimeoutRef = useRef<number | null>(null);
  const [animatedMessageIds, setAnimatedMessageIds] = useState<string[]>([]);
  const isImmersive = variant === "immersive";
  const resolvedEmptyTitle = emptyTitle ?? t("sessions.detail.emptyTitle");
  const resolvedEmptyDescription = emptyDescription ?? t("sessions.detail.emptyDescription");
  const resolvedWidthClassName =
    contentWidthClassName ?? (isImmersive ? "max-w-[62rem]" : "max-w-[52rem]");
  const messagesLabel = detail
    ? getPluralLabel(t, "sessions.page.totals.messages", detail.totals.messages)
    : null;
  const executionsLabel = detail
    ? getPluralLabel(t, "sessions.page.totals.executions", detail.totals.executions)
    : null;
  const orphanSection =
    detail?.orphan_executions.length ? (
      <section className="border-t border-[var(--border-subtle)] pt-5">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          <TimerReset className="h-3.5 w-3.5" />
          {t("sessions.detail.orphanEvents")}
        </div>
        <div className="mt-3 space-y-2">
          {detail.orphan_executions.map((execution) => (
            <SessionExecutionInline key={execution.task_id} execution={execution} />
          ))}
        </div>
      </section>
    ) : null;

  useEffect(() => {
    return () => {
      if (animationTimeoutRef.current != null) {
        window.clearTimeout(animationTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!detail) return;

    const ids = detail.messages.map((message) => message.id);
    const seen = seenMessageIdsRef.current;

    if (seen.size === 0) {
      seenMessageIdsRef.current = new Set(ids);
      window.requestAnimationFrame(() => {
        const element = bodyRef.current;
        if (!element) return;
        element.scrollTop = element.scrollHeight;
      });
      return;
    }

    const nextAnimatedIds = ids.filter((id) => !seen.has(id));
    ids.forEach((id) => seen.add(id));

    if (nextAnimatedIds.length === 0) return;

    setAnimatedMessageIds(nextAnimatedIds);
    if (animationTimeoutRef.current != null) {
      window.clearTimeout(animationTimeoutRef.current);
    }
    animationTimeoutRef.current = window.setTimeout(() => {
      setAnimatedMessageIds([]);
    }, 380);

    if (!shouldStickToBottomRef.current) return;

    window.requestAnimationFrame(() => {
      const element = bodyRef.current;
      if (!element) return;
      element.scrollTo({
        top: element.scrollHeight,
        behavior: "smooth",
      });
    });
  }, [detail]);

  if (loading && !detail) {
    return (
      <div className={cn("relative flex h-full min-h-0 flex-col", className)}>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={t("sessions.detail.close")}
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-6">
          <div className={cn("mx-auto space-y-5", resolvedWidthClassName)}>
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="skeleton h-28 w-full rounded-lg" />
            ))}
          </div>
        </div>
        {footer ? <div className="border-t border-[var(--border-subtle)]">{footer}</div> : null}
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div
        className={cn(
          "flex h-full min-h-0 flex-col items-center justify-center px-6 text-center",
          className
        )}
      >
        <MessageSquareText className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {t("sessions.detail.loadError")}
        </p>
        <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">{error}</p>
        {footer ? <div className="mt-auto w-full border-t border-[var(--border-subtle)]">{footer}</div> : null}
      </div>
    );
  }

  if (!detail) {
    return (
      <div
        className={cn(
          "flex h-full min-h-0 flex-col items-center justify-center px-6 text-center",
          className
        )}
      >
        <MessageSquareText className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {resolvedEmptyTitle}
        </p>
        <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
          {resolvedEmptyDescription}
        </p>
        {footer ? <div className="mt-auto w-full border-t border-[var(--border-subtle)]">{footer}</div> : null}
      </div>
    );
  }

  return (
    <div className={cn("relative flex h-full min-h-0 flex-col", className)}>
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          className="app-surface-close"
          aria-label={t("sessions.detail.close")}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
      <div
        ref={bodyRef}
        className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.015)_0%,transparent_26%)] px-5 py-6 sm:px-6"
        onScroll={(event) => {
          const element = event.currentTarget;
          const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
          shouldStickToBottomRef.current = distanceToBottom < 40;
        }}
      >
        <div
          className={cn(
            "mx-auto flex w-full flex-col gap-5",
            resolvedWidthClassName,
            bodyClassName
          )}
        >
          {showSummaryCard ? (
            <div className="app-card-row">
              <div className="flex flex-wrap items-center gap-2">
                <span className="app-card-row__eyebrow">{t("sessions.detail.conversation")}</span>
                <span className="rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.018)] px-2.5 py-1 text-[10px] font-semibold text-[var(--text-secondary)]">
                  {getBotLabel(detail.summary.bot_id)}
                </span>
              </div>
              <h2 className="app-card-row__title">
                {detail.summary.name || detail.summary.latest_message_preview || t("sessions.detail.sessionInProgress")}
              </h2>
              <div className="app-card-row__meta">
                <span>{messagesLabel}</span>
                <span>{executionsLabel}</span>
                <span>{formatCost(detail.totals.cost_usd)}</span>
                {detail.summary.last_activity_at ? (
                  <span>{formatRelativeTime(detail.summary.last_activity_at)}</span>
                ) : null}
              </div>
            </div>
          ) : null}

          {isImmersive ? orphanSection : null}

          {detail.messages.length === 0 ? (
            <div className="app-note">
              <p className="text-sm text-[var(--text-secondary)]">
                {t("sessions.detail.noMessagesYet")}
              </p>
            </div>
          ) : (
            detail.messages.map((message) => (
              <SessionMessageBubble
                key={message.id}
                message={message}
                animate={animatedMessageIds.includes(message.id)}
                botId={detail.summary.bot_id}
                variant={variant}
              />
            ))
          )}

          {!isImmersive ? orphanSection : null}
        </div>
      </div>
      {footer ? <div className="border-t border-[var(--border-subtle)]">{footer}</div> : null}
    </div>
  );
}
