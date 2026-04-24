"use client";

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ArrowDown, MessageSquareText } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { AssistantMessage } from "@/components/sessions/chat/assistant-message";
import { DaySeparator } from "@/components/sessions/chat/day-separator";
import { MessageTurn } from "@/components/sessions/chat/message-turn";
import { ThinkingIndicator } from "@/components/sessions/chat/thinking-indicator";
import { UserMessage } from "@/components/sessions/chat/user-message";
import type { ExecutionSummary, SessionMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface PendingChatMessage extends SessionMessage {
  requestId: string;
  clientState: "pending" | "failed";
  placeholderKind?: "assistant";
  retryText?: string;
}

interface ChatThreadProps {
  messages: SessionMessage[];
  pendingMessages?: PendingChatMessage[];
  orphanExecutions?: ExecutionSummary[];
  showThinking?: boolean;
  loading?: boolean;
  error?: string | null;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyEyebrow?: string | null;
  agentLabel?: string | null;
  onRetryPending?: (requestId: string) => void;
  onOpenExecution?: (taskId: number) => void;
  onLoadOlder?: () => void | Promise<void>;
  hasOlder?: boolean;
  loadingOlder?: boolean;
  onScrollStateChange?: (scrolled: boolean) => void;
  footer?: ReactNode;
  agentId?: string | null;
  sessionId?: string | null;
}

type ThreadItem =
  | { kind: "message"; message: SessionMessage | PendingChatMessage; key: string }
  | { kind: "separator"; label: string; key: string }
  | { kind: "orphan"; execution: ExecutionSummary; key: string };

function formatDayLabel(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function isPending(message: SessionMessage | PendingChatMessage): message is PendingChatMessage {
  return "requestId" in message;
}

function ChatThreadImpl({
  messages,
  pendingMessages = [],
  orphanExecutions = [],
  showThinking = false,
  loading = false,
  error,
  emptyTitle,
  emptyDescription,
  emptyEyebrow,
  agentLabel,
  onRetryPending,
  onOpenExecution,
  onLoadOlder,
  hasOlder = false,
  loadingOlder = false,
  onScrollStateChange,
  footer,
  agentId,
  sessionId,
}: ChatThreadProps) {
  const { t } = useAppI18n();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const prependAnchorRef = useRef<{ scrollTop: number; scrollHeight: number } | null>(null);
  const loadOlderLockRef = useRef(false);
  const previousItemCountRef = useRef(0);
  const scrolledPastTopRef = useRef(false);
  const [stuckToBottom, setStuckToBottom] = useState(true);

  const items: ThreadItem[] = useMemo(() => {
    const combined: Array<SessionMessage | PendingChatMessage> = [
      ...messages,
      ...pendingMessages,
    ].sort((a, b) => {
      const aTime = a.timestamp ? new Date(a.timestamp).getTime() : Number.MAX_SAFE_INTEGER;
      const bTime = b.timestamp ? new Date(b.timestamp).getTime() : Number.MAX_SAFE_INTEGER;
      if (aTime !== bTime) return aTime - bTime;
      return a.id.localeCompare(b.id);
    });

    const result: ThreadItem[] = [];
    let lastLabel: string | null = null;
    for (const entry of combined) {
      const label = formatDayLabel(entry.timestamp);
      if (label && label !== lastLabel) {
        result.push({ kind: "separator", label, key: `sep-${entry.id}` });
        lastLabel = label;
      }
      result.push({ kind: "message", message: entry, key: entry.id });
    }
    for (const execution of orphanExecutions) {
      result.push({
        kind: "orphan",
        execution,
        key: `orphan-${execution.task_id}`,
      });
    }
    return result;
  }, [messages, pendingMessages, orphanExecutions]);

  const handleScroll = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const distanceFromBottom = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    const nextStuck = distanceFromBottom <= 96;
    setStuckToBottom((current) => (current === nextStuck ? current : nextStuck));

    const nextScrolledPastTop = viewport.scrollTop > 16;
    if (nextScrolledPastTop !== scrolledPastTopRef.current) {
      scrolledPastTopRef.current = nextScrolledPastTop;
      onScrollStateChange?.(nextScrolledPastTop);
    }

    if (viewport.scrollTop <= 120 && hasOlder && !loadingOlder && onLoadOlder && !loadOlderLockRef.current) {
      loadOlderLockRef.current = true;
      prependAnchorRef.current = {
        scrollHeight: viewport.scrollHeight,
        scrollTop: viewport.scrollTop,
      };
      void onLoadOlder();
    }
  }, [hasOlder, loadingOlder, onLoadOlder, onScrollStateChange]);

  useEffect(() => {
    if (!loadingOlder) loadOlderLockRef.current = false;
  }, [loadingOlder]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const anchor = prependAnchorRef.current;
    if (anchor) {
      const delta = viewport.scrollHeight - anchor.scrollHeight;
      if (delta !== 0) {
        viewport.scrollTop = anchor.scrollTop + delta;
      }
      if (!loadingOlder) prependAnchorRef.current = null;
      previousItemCountRef.current = items.length;
      return;
    }

    if (items.length > previousItemCountRef.current && stuckToBottom) {
      viewport.scrollTop = viewport.scrollHeight;
    }
    previousItemCountRef.current = items.length;
  }, [items.length, loadingOlder, stuckToBottom]);

  const scrollToBottom = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
    setStuckToBottom(true);
  }, []);

  const hasConversation = items.length > 0;
  const showNewIndicator = !stuckToBottom && hasConversation;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--canvas)]">
      <div
        ref={viewportRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {loading && !hasConversation ? (
          <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8 px-6 pt-10 pb-8">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className={cn(
                  "h-16 w-full animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]",
                  index % 2 === 1 && "ml-auto max-w-[70%]",
                )}
              />
            ))}
          </div>
        ) : error && !hasConversation ? (
          <div className="mx-auto flex h-full w-full max-w-[480px] flex-col items-center justify-center gap-3 px-6 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]">
              <MessageSquareText className="icon-md" strokeWidth={1.75} />
            </span>
            <p className="m-0 text-[var(--font-size-md)] font-medium text-[var(--text-primary)]">
              {t("chat.thread.errorGeneric", { defaultValue: "Something went wrong." })}
            </p>
            <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">{error}</p>
          </div>
        ) : !hasConversation ? (
          <div className="mx-auto flex h-full w-full max-w-[680px] flex-col items-center justify-center gap-4 px-6 text-center">
            <p className="m-0 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {emptyEyebrow ??
                agentLabel ??
                t("sessions.thread.newChatEyebrow", { defaultValue: "New conversation" })}
            </p>
            <h1 className="display-serif m-0 text-[var(--font-size-display)] font-medium leading-[1.05] text-[var(--text-primary)]">
              {emptyTitle ??
                t("sessions.thread.heroTitle", { defaultValue: "What could we build today?" })}
            </h1>
            <p className="m-0 max-w-[480px] text-[var(--font-size-sm)] leading-[1.55] text-[var(--text-tertiary)]">
              {emptyDescription ??
                t("sessions.thread.heroHelper", {
                  defaultValue:
                    "Describe a task. Your agent responds with reasoning, tool calls, and artifacts.",
                })}
            </p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8 px-6 pt-10 pb-8">
            {loadingOlder ? (
              <div className="flex justify-center">
                <span className="chat-thinking-dots" aria-hidden>
                  <span />
                  <span />
                  <span />
                </span>
              </div>
            ) : null}
            {items.map((item) => {
              if (item.kind === "separator") {
                return <DaySeparator key={item.key} label={item.label} />;
              }
              if (item.kind === "orphan") {
                return (
                  <MessageTurn key={item.key} role="assistant">
                    <AssistantMessage
                      text=""
                      linkedExecution={item.execution}
                      onOpenExecution={onOpenExecution}
                      agentId={agentId}
                      sessionId={sessionId}
                    />
                  </MessageTurn>
                );
              }
              const message = item.message;
              const pending = isPending(message);
              const failed = pending && message.clientState === "failed";
              if (message.role === "user") {
                return (
                  <MessageTurn
                    key={item.key}
                    role="user"
                    timestamp={message.timestamp}
                    failed={failed}
                    onRetry={
                      failed && pending && onRetryPending
                        ? () => onRetryPending(message.requestId)
                        : undefined
                    }
                  >
                    <UserMessage
                      text={message.text || ""}
                      pending={pending && message.clientState === "pending"}
                      failed={failed}
                    />
                  </MessageTurn>
                );
              }
              const placeholderPending =
                pending && message.placeholderKind === "assistant" && !message.text.trim();
              if (placeholderPending) {
                return <ThinkingIndicator key={item.key} />;
              }
              return (
                <MessageTurn
                  key={item.key}
                  role="assistant"
                  timestamp={message.timestamp}
                >
                  <AssistantMessage
                    text={message.text}
                    linkedExecution={message.linked_execution ?? null}
                    onOpenExecution={onOpenExecution}
                    agentId={agentId}
                    sessionId={sessionId}
                  />
                </MessageTurn>
              );
            })}
            {showThinking ? <ThinkingIndicator /> : null}
          </div>
        )}
      </div>

      {showNewIndicator ? (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-[120px] left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-[color:var(--border-subtle)] bg-[var(--panel-strong)] px-3 py-1.5 text-[0.75rem] text-[var(--text-secondary)] shadow-[var(--shadow-floating)] transition-colors hover:text-[var(--text-primary)]"
        >
          <ArrowDown className="icon-xs" strokeWidth={1.75} aria-hidden />
          {t("chat.thread.newMessages", { defaultValue: "New messages" })}
        </button>
      ) : null}

      {footer ? <div className="shrink-0">{footer}</div> : null}
    </div>
  );
}

export const ChatThread = memo(ChatThreadImpl);
