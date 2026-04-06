"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { Info, LoaderCircle, MessageSquareText, PanelLeft, RotateCcw } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import type { SessionDetail, SessionMessage, SessionSummary } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

export interface PendingSessionMessage extends SessionMessage {
  requestId: string;
  clientState: "pending" | "failed";
  placeholderKind?: "assistant";
  retryText?: string;
}

interface SessionThreadViewProps {
  botId?: string;
  hasSelectedSession?: boolean;
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  historyMessages?: SessionMessage[];
  pendingMessages?: PendingSessionMessage[];
  loading?: boolean;
  transitioning?: boolean;
  loadingOlderHistory?: boolean;
  hasOlderHistory?: boolean;
  onLoadOlderHistory?: () => void | Promise<void>;
  error?: string | null;
  showRailToggle?: boolean;
  onOpenRail?: () => void;
  showContextToggle?: boolean;
  onOpenContext?: () => void;
  onRetryPendingMessage?: (requestId: string) => void;
  footer?: React.ReactNode;
}

function isPendingMessage(
  message: SessionMessage | PendingSessionMessage,
): message is PendingSessionMessage {
  return "requestId" in message;
}

type ThreadRenderable =
  | {
      kind: "message";
      message: SessionMessage | PendingSessionMessage;
    }
  | {
      kind: "separator";
      id: string;
      label: string;
    };

function PendingDots() {
  return (
    <span className="inline-flex items-center gap-1 text-[var(--text-tertiary)]">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:-0.2s]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:-0.05s]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:0.1s]" />
    </span>
  );
}

function formatThreadDayLabel(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function resolveConversationModel(messages: SessionMessage[], detail: SessionDetail | null) {
  const candidates = [...messages, ...(detail?.messages ?? [])];
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const current = candidates[index];
    const resolvedModel =
      current.model?.trim() || current.linked_execution?.model?.trim() || null;
    if (resolvedModel) {
      return resolvedModel;
    }
  }
  return null;
}

function formatConversationModelLabel(value: string | null) {
  if (!value) return null;
  const compact = value.trim();
  if (!compact) return null;
  return compact.replace(/[_]+/g, "-");
}

function useThreadItems(
  historyMessages: SessionMessage[],
  pendingMessages: PendingSessionMessage[],
) {
  return useMemo<ThreadRenderable[]>(() => {
    const items = [...historyMessages, ...pendingMessages].sort((left, right) => {
      const leftTime = left.timestamp ? new Date(left.timestamp).getTime() : Number.MAX_SAFE_INTEGER;
      const rightTime = right.timestamp ? new Date(right.timestamp).getTime() : Number.MAX_SAFE_INTEGER;
      if (leftTime !== rightTime) return leftTime - rightTime;
      return left.id.localeCompare(right.id);
    });

    const renderables: ThreadRenderable[] = [];
    let lastLabel: string | null = null;
    for (const item of items) {
      const dayLabel = formatThreadDayLabel(item.timestamp);
      if (dayLabel && dayLabel !== lastLabel) {
        renderables.push({
          kind: "separator",
          id: `separator-${item.id}`,
          label: dayLabel,
        });
        lastLabel = dayLabel;
      }
      renderables.push({ kind: "message", message: item });
    }
    return renderables;
  }, [historyMessages, pendingMessages]);
}

function ThreadMessage({
  message,
  botId,
  onRetry,
}: {
  message: SessionMessage | PendingSessionMessage;
  botId?: string;
  onRetry?: () => void;
}) {
  const { t } = useAppI18n();
  const isAssistant = message.role === "assistant";
  const isPending = "clientState" in message && message.clientState === "pending";
  const isFailed = "clientState" in message && message.clientState === "failed";
  const botColor = getBotColor(botId || "");
  const bubbleClassName = isAssistant
    ? "border-[color-mix(in_srgb,var(--border-subtle)_84%,transparent)] bg-[color-mix(in_srgb,var(--surface-panel-soft) 94%,var(--surface-canvas))]"
    : "border-[color-mix(in_srgb,var(--tone-info-border)_44%,transparent)] bg-[color-mix(in_srgb,var(--tone-info-bg)_54%,var(--surface-canvas))]";

  return (
    <div className={cn("flex w-full gap-3", isAssistant ? "justify-start" : "justify-end")}>
      {isAssistant ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
          {botId ? (
            <BotAgentGlyph
              botId={botId}
              color={botColor}
              active
              variant="list"
              shape="swatch"
              className="h-6 w-6"
            />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--text-quaternary)]" />
          )}
        </div>
      ) : null}

      <div className={cn("max-w-[min(100%,46rem)]", !isAssistant && "flex flex-col items-end")}>
        <div
          className={cn(
            "rounded-[1.25rem] border px-4 py-3.5",
            bubbleClassName,
            isFailed && "border-[color-mix(in_srgb,var(--tone-danger-border)_72%,transparent)]",
            isPending && "opacity-90"
          )}
        >
          {"placeholderKind" in message && message.placeholderKind === "assistant" && isPending ? (
            <div className="flex items-center gap-3">
              <PendingDots />
              <span className="text-sm text-[var(--text-tertiary)]">
                {t("sessions.thread.waitingForReply", { defaultValue: "Waiting for the bot reply..." })}
              </span>
            </div>
          ) : (
            <SessionRichText content={message.text} variant={isAssistant ? "assistant" : "user"} />
          )}
        </div>

        <div className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-[var(--text-quaternary)]">
          {message.timestamp ? <span>{formatRelativeTime(message.timestamp)}</span> : null}
          {isPending ? (
            <>
              <span>•</span>
              <span>{t("sessions.thread.pending", { defaultValue: "Pending" })}</span>
            </>
          ) : null}
          {isFailed ? (
            <>
              <span>•</span>
              <span className="text-[var(--tone-danger-dot)]">
                {t("sessions.thread.failed", { defaultValue: "Failed to send" })}
              </span>
            </>
          ) : null}
        </div>

        {isFailed && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t("sessions.thread.retry", { defaultValue: "Retry" })}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function SessionThreadView(props: SessionThreadViewProps) {
  const {
    botId,
    hasSelectedSession = false,
    detail,
    summary,
    historyMessages = [],
    pendingMessages = [],
    loading = false,
    transitioning = false,
    loadingOlderHistory = false,
    hasOlderHistory = false,
    onLoadOlderHistory,
    error,
    showRailToggle = false,
    onOpenRail,
    showContextToggle = false,
    onOpenContext,
    onRetryPendingMessage,
    footer,
  } = props;
  const { t } = useAppI18n();
  const items = useThreadItems(historyMessages, pendingMessages);
  const hasConversation = historyMessages.length > 0 || pendingMessages.length > 0;
  const headerBotId = detail?.summary.bot_id ?? summary?.bot_id ?? botId ?? null;
  const headerBotLabel = headerBotId ? getBotLabel(headerBotId) : null;
  const headerBotColor = headerBotId ? getBotColor(headerBotId) : "#7A8799";
  const headerModelLabel = formatConversationModelLabel(
    resolveConversationModel(historyMessages, detail)
  );
  const hasThreadHeader = Boolean(headerBotId && headerBotLabel);
  const threadViewportRef = useRef<HTMLDivElement | null>(null);
  const prependAnchorRef = useRef<{ scrollHeight: number; scrollTop: number } | null>(null);
  const loadOlderLockRef = useRef(false);
  const autoStickToBottomRef = useRef(true);
  const previousConversationKeyRef = useRef<string | null>(null);
  const previousItemCountRef = useRef(0);
  const conversationKey =
    detail?.summary.session_id ??
    summary?.session_id ??
    pendingMessages[0]?.session_id ??
    null;

  const requestOlderHistory = useCallback(() => {
    const viewport = threadViewportRef.current;
    if (!viewport || !hasOlderHistory || loadingOlderHistory || !onLoadOlderHistory) {
      return;
    }
    if (loadOlderLockRef.current) {
      return;
    }

    loadOlderLockRef.current = true;
    prependAnchorRef.current = {
      scrollHeight: viewport.scrollHeight,
      scrollTop: viewport.scrollTop,
    };
    void onLoadOlderHistory();
  }, [hasOlderHistory, loadingOlderHistory, onLoadOlderHistory]);

  const handleViewportScroll = useCallback(() => {
    const viewport = threadViewportRef.current;
    if (!viewport) return;

    const distanceFromBottom =
      viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    autoStickToBottomRef.current = distanceFromBottom <= 96;

    if (viewport.scrollTop <= 120) {
      requestOlderHistory();
    }
  }, [requestOlderHistory]);

  useEffect(() => {
    if (!loadingOlderHistory) {
      loadOlderLockRef.current = false;
    }
  }, [loadingOlderHistory]);

  useEffect(() => {
    const viewport = threadViewportRef.current;
    if (!viewport || !hasConversation) return;
    if (hasOlderHistory && !loadingOlderHistory && viewport.scrollHeight <= viewport.clientHeight + 32) {
      requestOlderHistory();
    }
  }, [hasConversation, hasOlderHistory, items.length, loadingOlderHistory, requestOlderHistory]);

  useLayoutEffect(() => {
    const viewport = threadViewportRef.current;
    const anchor = prependAnchorRef.current;
    if (!viewport || !anchor) return;

    const delta = viewport.scrollHeight - anchor.scrollHeight;
    if (delta !== 0) {
      viewport.scrollTop = anchor.scrollTop + delta;
      anchor.scrollTop = viewport.scrollTop;
      anchor.scrollHeight = viewport.scrollHeight;
    }

    if (!loadingOlderHistory) {
      prependAnchorRef.current = null;
    }
  }, [items.length, loadingOlderHistory]);

  useLayoutEffect(() => {
    const viewport = threadViewportRef.current;
    if (!viewport) return;

    if (previousConversationKeyRef.current !== conversationKey) {
      viewport.scrollTop = viewport.scrollHeight;
      previousConversationKeyRef.current = conversationKey;
      previousItemCountRef.current = items.length;
      autoStickToBottomRef.current = true;
      prependAnchorRef.current = null;
      loadOlderLockRef.current = false;
      return;
    }

    if (!prependAnchorRef.current && items.length > previousItemCountRef.current && autoStickToBottomRef.current) {
      viewport.scrollTop = viewport.scrollHeight;
    }

    previousItemCountRef.current = items.length;
  }, [conversationKey, items.length]);

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--surface-canvas)]">
      {transitioning ? (
        <div className="pointer-events-none absolute left-1/2 top-4 z-20 -translate-x-1/2">
          <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--text-secondary)]">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            {t("sessions.thread.loadingConversation", {
              defaultValue: "Loading conversation...",
            })}
          </span>
        </div>
      ) : null}

      {showRailToggle || showContextToggle ? (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between px-4 py-4 sm:px-6">
          <div className="pointer-events-auto flex items-center gap-2">
            {showRailToggle ? (
              <button
                type="button"
                onClick={onOpenRail}
                className="button-shell button-shell--secondary button-shell--icon h-10 w-10 text-[var(--text-secondary)] lg:hidden"
                aria-label={t("sessions.page.botConversations")}
              >
                <PanelLeft className="h-4 w-4" />
              </button>
            ) : null}
          </div>

          <div className="pointer-events-auto flex items-center gap-2">
            {showContextToggle ? (
              <button
                type="button"
                onClick={onOpenContext}
                className="button-shell button-shell--secondary button-shell--icon h-10 w-10 text-[var(--text-secondary)] xl:hidden"
                aria-label={t("sessions.page.conversationInfo", { defaultValue: "Conversation info" })}
              >
                <Info className="h-4 w-4" />
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasThreadHeader ? (
        <div
          className={cn(
            "shrink-0 border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 pb-3 sm:px-6",
            (showRailToggle || showContextToggle) ? "pt-20 sm:pt-20" : "pt-4"
          )}
          aria-label={t("sessions.thread.activeBot", {
            defaultValue: "Conversation bot",
          })}
        >
          <div className="mx-auto flex w-full max-w-[52rem] items-center gap-3">
            <BotAgentGlyph
              botId={headerBotId!}
              color={headerBotColor}
              active
              variant="list"
              shape="swatch"
              className="h-9 w-9 shrink-0 bot-swatch--animated"
            />
            <div className="min-w-0">
              <p className="truncate text-[15px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
                {headerBotLabel}
              </p>
              <p className="truncate text-[12px] text-[var(--text-tertiary)]">
                {headerModelLabel ??
                  t("sessions.thread.modelUnknown", {
                    defaultValue: "Model not informed",
                  })}
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <div
        ref={threadViewportRef}
        onScroll={handleViewportScroll}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 transition-opacity duration-200 sm:px-6",
          transitioning && "opacity-80",
          (showRailToggle || showContextToggle) && !hasThreadHeader && "pt-20 sm:pt-20"
        )}
      >
        {(loading || transitioning) && !hasConversation ? (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className={cn(
                  "skeleton h-24 rounded-[1.2rem]",
                  index % 2 === 0 ? "w-[min(100%,38rem)]" : "ml-auto w-[min(100%,30rem)]"
                )}
              />
            ))}
          </div>
        ) : error && !hasConversation ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <MessageSquareText className="h-10 w-10 text-[var(--text-tertiary)]" />
            <p className="mt-4 text-lg font-semibold text-[var(--text-primary)]">
              {t("sessions.detail.loadError")}
            </p>
            <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-12 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-[1.5rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
              <MessageSquareText className="h-7 w-7 text-[var(--text-tertiary)]" />
            </div>
            <p className="mt-5 text-[1.35rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {hasSelectedSession
                ? t("sessions.thread.emptySelectedTitle", {
                    defaultValue: "No messages recovered yet",
                  })
                : botId
                ? t("sessions.thread.startConversationTitle", {
                    defaultValue: "Start a new conversation",
                  })
                : t("sessions.thread.noBotTitle", {
                    defaultValue: "Select a specific bot",
                  })}
            </p>
            <p className="mt-2 max-w-xl text-[15px] leading-7 text-[var(--text-secondary)]">
              {hasSelectedSession
                ? t("sessions.thread.emptySelectedDescription", {
                    defaultValue: "This session is selected, but no recoverable transcript messages are available yet.",
                  })
                : botId
                ? t("sessions.thread.startConversationDescription", {
                    defaultValue: "Use the composer below to begin a fresh conversation or choose a previous session from the inbox.",
                  })
                : t("sessions.thread.noBotDescription", {
                    defaultValue: "Choose a bot in the inbox to open its history or start a new chat.",
                  })}
            </p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[52rem] flex-col gap-4">
            {loadingOlderHistory ? (
              <div className="flex justify-center py-1">
                <span className="session-thread__status-pill inline-flex items-center gap-2 px-3 py-1 text-[11px] font-medium text-[var(--text-tertiary)]">
                  <PendingDots />
                  {t("sessions.thread.loadingOlder", {
                    defaultValue: "Loading older messages...",
                  })}
                </span>
              </div>
            ) : null}
            {items.map((item) =>
              item.kind === "separator" ? (
                <div key={item.id} className="session-thread__separator-row">
                  <span className="session-thread__day-separator">
                    {item.label}
                  </span>
                </div>
              ) : (
                (() => {
                  const pendingMessage = isPendingMessage(item.message) ? item.message : null;
                  return (
                    <ThreadMessage
                      key={item.message.id}
                      message={item.message}
                      botId={detail?.summary.bot_id ?? botId}
                      onRetry={
                        pendingMessage && pendingMessage.clientState === "failed"
                          ? () => onRetryPendingMessage?.(pendingMessage.requestId)
                          : undefined
                      }
                    />
                  );
                })()
              )
            )}
          </div>
        )}
      </div>

      {footer ? <div className="shrink-0 bg-[var(--surface-canvas)]">{footer}</div> : null}
    </section>
  );
}
