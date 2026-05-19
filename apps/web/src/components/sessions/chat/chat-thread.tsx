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
import { ArrowDown, LoaderCircle, MessageSquareText } from "lucide-react";
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

const TOP_LOAD_THRESHOLD_PX = 320;

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
  const footerResizeObserverRef = useRef<ResizeObserver | null>(null);
  const prependAnchorRef = useRef<{ scrollTop: number; scrollHeight: number } | null>(null);
  const loadOlderLockRef = useRef(false);
  const previousItemCountRef = useRef(0);
  const scrolledPastTopRef = useRef(false);
  const [stuckToBottom, setStuckToBottom] = useState(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [footerHeight, setFooterHeight] = useState(0);

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

  const triggerLoadOlder = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || !hasOlder || loadingOlder || !onLoadOlder || loadOlderLockRef.current) {
      return;
    }
    loadOlderLockRef.current = true;
    prependAnchorRef.current = {
      scrollHeight: viewport.scrollHeight,
      scrollTop: viewport.scrollTop,
    };
    void Promise.resolve(onLoadOlder()).finally(() => {
      loadOlderLockRef.current = false;
    });
  }, [hasOlder, loadingOlder, onLoadOlder]);

  const handleScroll = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const distanceFromBottom = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    const canScroll = viewport.scrollHeight > viewport.clientHeight + 8;
    const nextStuck = distanceFromBottom <= 96;
    setStuckToBottom((current) => (current === nextStuck ? current : nextStuck));
    const nextShowJump = canScroll && distanceFromBottom > 160;
    setShowJumpToBottom((current) => (current === nextShowJump ? current : nextShowJump));

    const nextScrolledPastTop = viewport.scrollTop > 16;
    if (nextScrolledPastTop !== scrolledPastTopRef.current) {
      scrolledPastTopRef.current = nextScrolledPastTop;
      onScrollStateChange?.(nextScrolledPastTop);
    }

    if (viewport.scrollTop <= TOP_LOAD_THRESHOLD_PX) {
      triggerLoadOlder();
    }
  }, [onScrollStateChange, triggerLoadOlder]);

  useEffect(() => {
    if (!loadingOlder) loadOlderLockRef.current = false;
  }, [loadingOlder]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || !hasOlder || loadingOlder) return;
    if (viewport.clientHeight <= 0) return;
    if (viewport.scrollTop <= TOP_LOAD_THRESHOLD_PX) {
      triggerLoadOlder();
    }
  }, [hasOlder, items.length, loadingOlder, triggerLoadOlder]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || items.length === 0) return;
    if (viewport.clientHeight <= 0) return;
    if (viewport.scrollHeight <= viewport.clientHeight + TOP_LOAD_THRESHOLD_PX) {
      triggerLoadOlder();
    }
  }, [items.length, triggerLoadOlder]);

  const bindFooterElement = useCallback((footerElement: HTMLDivElement | null) => {
    footerResizeObserverRef.current?.disconnect();
    footerResizeObserverRef.current = null;
    if (!footerElement) {
      setFooterHeight(0);
      return;
    }

    const measure = () => {
      const nextHeight = Math.ceil(footerElement.getBoundingClientRect().height);
      setFooterHeight((current) => (current === nextHeight ? current : nextHeight));
    };

    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(footerElement);
    footerResizeObserverRef.current = observer;
  }, []);

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
    setShowJumpToBottom(false);
  }, []);

  const hasConversation = items.length > 0;
  const showNewIndicator = showJumpToBottom && hasConversation;
  const loadingLabel = t("chat.thread.loading", { defaultValue: "Loading conversation" });

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--canvas)]">
      <div
        ref={viewportRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-busy={loading || loadingOlder ? true : undefined}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {loading && !hasConversation ? (
          <div
            role="status"
            aria-label={loadingLabel}
            className="mx-auto flex w-full max-w-[960px] flex-col gap-5 px-6 pt-8 pb-8 lg:px-10"
          >
            <div className="flex justify-center pb-1">
              <LoaderCircle className="h-4 w-4 animate-spin text-[var(--text-tertiary)]" strokeWidth={2} aria-hidden />
            </div>
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className={cn(
                  "grid w-full animate-pulse grid-cols-[2.5rem_minmax(0,1fr)] gap-3 rounded-[var(--radius-panel-sm)] px-2 py-1.5",
                  index % 2 === 1 && "ml-auto max-w-[70%]",
                )}
              >
                <span className="h-9 w-9 rounded-[0.65rem] bg-[var(--panel-soft)]" aria-hidden />
                <span className="flex min-w-0 flex-col gap-2 pt-0.5" aria-hidden>
                  <span className="h-3 w-32 rounded-full bg-[var(--panel-soft)]" />
                  <span className="h-3 w-full max-w-[34rem] rounded-full bg-[var(--panel-soft)]" />
                  <span className="h-3 w-2/3 rounded-full bg-[var(--panel-soft)]" />
                </span>
              </div>
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
          <div className="mx-auto flex h-full w-full max-w-[620px] flex-col items-center justify-center gap-3 px-6 text-center">
            <p className="m-0 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {emptyEyebrow ??
                agentLabel ??
                t("sessions.thread.newChatEyebrow", { defaultValue: "New conversation" })}
            </p>
            <h1 className="m-0 text-[1.5rem] font-medium leading-[1.15] text-[var(--text-primary)] sm:text-[1.75rem]">
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
          <div className="mx-auto flex w-full max-w-[960px] flex-col gap-6 px-6 pt-8 pb-8 lg:px-10">
            {loading ? (
              <div className="sticky top-3 z-10 flex justify-center">
                <span
                  role="status"
                  aria-label={loadingLabel}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[color:var(--divider-hair)] bg-[var(--panel)] text-[var(--text-tertiary)] shadow-[var(--shadow-xs)] backdrop-blur"
                >
                  <LoaderCircle className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden />
                </span>
              </div>
            ) : null}
            {loadingOlder ? (
              <div className="flex justify-center">
                <LoaderCircle
                  className="h-4 w-4 animate-spin text-[var(--text-tertiary)]"
                  aria-label={t("sessions.thread.loadingOlder", {
                    defaultValue: "Loading older messages",
                  })}
                  strokeWidth={1.75}
                />
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
                    artifacts={message.artifacts ?? []}
                    blocks={"blocks" in message ? message.blocks : undefined}
                  />
                </MessageTurn>
              );
            })}
            {showThinking ? <ThinkingIndicator /> : null}
          </div>
        )}
      </div>

      {showNewIndicator ? (
        <div
          className="pointer-events-none absolute left-1/2 z-20 -translate-x-1/2"
          style={{ bottom: `${Math.max(16, footerHeight + 12)}px` }}
        >
          <button
            type="button"
            onClick={scrollToBottom}
            className={cn(
              "pointer-events-auto !inline-flex !h-9 !w-9 !min-w-9 !max-w-9 shrink-0 items-center justify-center rounded-full",
              "border border-[color:var(--border-subtle)] bg-[color:var(--panel)] text-[var(--text-secondary)] shadow-[var(--shadow-floating)] backdrop-blur",
              "transition-[background-color,border-color,color,transform] duration-[140ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--panel-strong)] hover:text-[var(--text-primary)] active:scale-[0.98]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
            )}
            style={{ width: 36, minWidth: 36, maxWidth: 36 }}
          >
            <ArrowDown className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
            <span className="sr-only">
              {t("chat.thread.newMessages", { defaultValue: "New messages" })}
            </span>
          </button>
        </div>
      ) : null}

      {footer ? (
        <div ref={bindFooterElement} className="shrink-0">
          {footer}
        </div>
      ) : null}
    </div>
  );
}

export const ChatThread = memo(ChatThreadImpl);
