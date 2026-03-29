"use client";

import { useMemo } from "react";
import { Info, MessageSquareText, PanelLeft, RotateCcw } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import type { ExecutionSummary, SessionDetail, SessionMessage, SessionSummary } from "@/lib/types";
import { cn, formatCost, formatDuration, formatRelativeTime } from "@/lib/utils";

export interface PendingSessionMessage extends SessionMessage {
  requestId: string;
  clientState: "pending" | "failed";
  placeholderKind?: "assistant";
  retryText?: string;
}

interface SessionThreadViewProps {
  botId?: string;
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  pendingMessages?: PendingSessionMessage[];
  loading?: boolean;
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

function SessionExecutionMeta({ execution }: { execution: ExecutionSummary }) {
  const feedbackStatus = execution.feedback_status?.trim() || null;
  const retrievalStrategy = execution.retrieval_strategy?.trim() || null;
  const answerGateStatus = execution.answer_gate_status?.trim() || null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
      <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] px-2 py-0.5">
        #{execution.task_id}
      </span>
      {execution.model ? <span>{execution.model}</span> : null}
      {execution.duration_ms != null ? <span>{formatDuration(execution.duration_ms)}</span> : null}
      {execution.tool_count > 0 ? <span>{execution.tool_count} tools</span> : null}
      <span>{formatCost(execution.cost_usd)}</span>
      {feedbackStatus ? (
        <span className="rounded-full border border-[rgba(130,255,186,0.18)] bg-[rgba(130,255,186,0.08)] px-2 py-0.5 text-[var(--text-secondary)]">
          {`feedback: ${feedbackStatus}`}
        </span>
      ) : null}
      {retrievalStrategy ? <span>{`provenance: ${retrievalStrategy}`}</span> : null}
      {answerGateStatus ? <span>{`gate: ${answerGateStatus}`}</span> : null}
      {execution.post_write_review_required ? <span>post-review required</span> : null}
    </div>
  );
}

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

function useThreadItems(
  detail: SessionDetail | null,
  pendingMessages: PendingSessionMessage[],
) {
  return useMemo<ThreadRenderable[]>(() => {
    const actualMessages = detail?.messages ?? [];
    const items = [...actualMessages, ...pendingMessages].sort((left, right) => {
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
  }, [detail?.messages, pendingMessages]);
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
    ? "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.035)]"
    : "border-[rgba(130,140,255,0.22)] bg-[rgba(110,120,255,0.14)]";

  return (
    <div className={cn("flex w-full gap-3", isAssistant ? "justify-start" : "justify-end")}>
      {isAssistant ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.025)]">
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
            "rounded-[1.35rem] border px-4 py-3 shadow-[0_16px_44px_rgba(0,0,0,0.18)]",
            bubbleClassName,
            isFailed && "border-[rgba(255,120,120,0.32)]",
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

          {message.linked_execution ? <SessionExecutionMeta execution={message.linked_execution} /> : null}
        </div>

        <div className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-[var(--text-tertiary)]">
          <span>{isAssistant ? (botId ? getBotLabel(botId) : t("common.bot")) : t("sessions.detail.you")}</span>
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
            className="mt-2 inline-flex items-center gap-2 rounded-full border border-[rgba(255,255,255,0.09)] bg-[rgba(255,255,255,0.035)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] transition-colors hover:bg-[rgba(255,255,255,0.06)]"
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
    detail,
    pendingMessages = [],
    loading = false,
    error,
    showRailToggle = false,
    onOpenRail,
    showContextToggle = false,
    onOpenContext,
    onRetryPendingMessage,
    footer,
  } = props;
  const { t } = useAppI18n();
  const items = useThreadItems(detail, pendingMessages);
  const hasConversation = Boolean(detail || pendingMessages.length);

  return (
    <section className="relative flex h-full min-h-0 flex-col bg-[#0b0c10]">
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

      <div
        className={cn(
          "min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6",
          (showRailToggle || showContextToggle) && "pt-20 sm:pt-20"
        )}
      >
        {loading && !hasConversation ? (
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
            <div className="flex h-16 w-16 items-center justify-center rounded-[1.5rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)]">
              <MessageSquareText className="h-7 w-7 text-[var(--text-tertiary)]" />
            </div>
            <p className="mt-5 text-[1.35rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {botId
                ? t("sessions.thread.startConversationTitle", {
                    defaultValue: "Start a new conversation",
                  })
                : t("sessions.thread.noBotTitle", {
                    defaultValue: "Select a specific bot",
                  })}
            </p>
            <p className="mt-2 max-w-xl text-[15px] leading-7 text-[var(--text-secondary)]">
              {botId
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
            {items.map((item) =>
              item.kind === "separator" ? (
                <div key={item.id} className="flex items-center gap-4 py-2">
                  <div className="h-px flex-1 bg-[rgba(255,255,255,0.06)]" />
                  <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
                    {item.label}
                  </span>
                  <div className="h-px flex-1 bg-[rgba(255,255,255,0.06)]" />
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

      {footer ? <div className="bg-[#0b0c10]">{footer}</div> : null}
    </section>
  );
}
