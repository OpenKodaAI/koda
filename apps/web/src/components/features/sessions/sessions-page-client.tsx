"use client";


import { Suspense, useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
  useMediaQuery,
} from "@/hooks/use-animated-presence";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAppTour } from "@/hooks/use-app-tour";
import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useContentStable } from "@/hooks/use-content-stable";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";
import { ChatHeader } from "@/components/sessions/chat/chat-header";
import { ChatThread, type PendingChatMessage } from "@/components/sessions/chat/chat-thread";
import { SessionContextDrawer } from "@/components/sessions/context/session-context-drawer";
import { SessionRail } from "@/components/sessions/rail/session-rail";
import { useSessionStream } from "@/hooks/use-session-stream";
import type { SessionStreamEvent } from "@/lib/contracts/sessions";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import type {
  SessionDetail,
  SessionMessage,
  SessionSendRequest,
  SessionSendResponse,
  SessionSummary,
} from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

const SESSION_FETCH_LIMIT = 200;
const SESSION_THREAD_PAGE_SIZE = 24;
const NEW_SESSION_PLACEHOLDER_ID = "__new_session__";

function normalizeSelectedBotId(
  candidate: string | null | undefined,
  availableBotIds: string[],
) {
  if (!candidate) return undefined;
  const match = availableBotIds.find((agentId) => agentId.toLowerCase() === candidate.toLowerCase());
  return match ?? undefined;
}

function mergeSessionHistoryPages(
  latestDetail: SessionDetail | null,
  olderDetails: SessionDetail[],
) {
  const orderedPages = [...olderDetails].reverse();
  if (latestDetail) {
    orderedPages.push(latestDetail);
  }

  const seen = new Set<string>();
  const messages: SessionMessage[] = [];
  for (const page of orderedPages) {
    for (const message of page.messages) {
      if (seen.has(message.id)) continue;
      seen.add(message.id);
      messages.push(message);
    }
  }
  return messages;
}

function resolveSessionTitle(summary: SessionSummary | null | undefined): string {
  if (!summary) return "";
  if (summary.name?.trim()) return summary.name.trim();
  if (summary.latest_query_preview?.trim()) return truncateText(summary.latest_query_preview.trim(), 52);
  if (summary.latest_message_preview?.trim()) return truncateText(summary.latest_message_preview.trim(), 52);
  return `Conversation ${summary.session_id.slice(0, 8)}`;
}

function SessionsPageContent() {
  const { t } = useAppI18n();
  const { currentStep, status } = useAppTour();
  const { agents } = useAgentCatalog();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const queryBotId = searchParams.get("agent");

  const [activeBotId, setActiveBotId] = useState<string | undefined>(() =>
    normalizeSelectedBotId(queryBotId, availableBotIds)
  );
  const [search, setSearch] = useState(searchParams.get("search") ?? "");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    searchParams.get("session")
  );
  const [isNewChatMode, setIsNewChatMode] = useState(false);
  const [draft, setDraft] = useState("");
  const [composerError, setComposerError] = useState<string | null>(null);
  const [composerSubmitting, setComposerSubmitting] = useState(false);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [contextDrawerOpen, setContextDrawerOpen] = useState(false);
  const [threadScrolled, setThreadScrolled] = useState(false);
  const [pendingMessages, setPendingMessages] = useState<PendingChatMessage[]>([]);
  const [olderDetailPages, setOlderDetailPages] = useState<SessionDetail[]>([]);
  const [loadingOlderDetailPages, setLoadingOlderDetailPages] = useState(false);
  const [pendingRequest, setPendingRequest] = useState<{
    requestId: string;
    text: string;
    sessionId: string;
    agentId: string;
    startedAt: number;
  } | null>(null);

  const queryClient = useQueryClient();
  const deferredSearch = useDeferredValue(search.trim());
  const debouncedSearch = useDebouncedValue(deferredSearch, 220);

  useEffect(() => {
    if (availableBotIds.length === 0) {
      setActiveBotId(undefined);
      return;
    }
    const normalizedQueryBotId = normalizeSelectedBotId(queryBotId, availableBotIds);
    setActiveBotId((current) => {
      if (queryBotId === null) {
        return current && availableBotIds.includes(current) ? current : undefined;
      }
      return normalizedQueryBotId;
    });
  }, [availableBotIds, queryBotId]);

  useEffect(() => {
    if (isDesktop) {
      setMobileRailOpen(false);
    }
  }, [isDesktop]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.innerWidth >= 768) return;
    if (status !== "running") return;

    const isRailStep = currentStep?.id === "tour.sessions.rail";
    const frame = window.requestAnimationFrame(() => {
      setMobileRailOpen(isRailStep);
    });

    return () => window.cancelAnimationFrame(frame);
  }, [currentStep?.id, status]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (activeBotId) {
      params.set("agent", activeBotId);
    } else {
      params.delete("agent");
    }
    if (search.trim()) {
      params.set("search", search.trim());
    } else {
      params.delete("search");
    }
    if (selectedSessionId) {
      params.set("session", selectedSessionId);
    } else {
      params.delete("session");
    }
    const nextQuery = params.toString();
    const currentQuery = searchParams.toString();
    if (nextQuery === currentQuery) return;
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }, [activeBotId, pathname, router, search, searchParams, selectedSessionId]);

  const sessionsQueryKey = queryKeys.dashboard.sessions({
    search: debouncedSearch,
    limit: SESSION_FETCH_LIMIT,
  });

  const sessionsQuery = useControlPlaneQuery<{
    items: SessionSummary[];
    unavailable: boolean;
  }>({
    tier: "live",
    queryKey: sessionsQueryKey,
    enabled: availableBotIds.length > 0,
    refetchInterval: 15_000,
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: async ({ signal }) => {
      const response = await fetchControlPlaneDashboardJsonAllowError<SessionSummary[]>(
        "/sessions",
        {
          signal,
          params: {
            limit: SESSION_FETCH_LIMIT,
            search: debouncedSearch || null,
          },
          fallbackError: t("sessions.loadError"),
        },
      );
      return {
        items: Array.isArray(response.data) ? response.data : [],
        unavailable: false,
      };
    },
  });

  const stableSessionsPayload = useContentStable(sessionsQuery.data);
  const sessions = useMemo(() => stableSessionsPayload?.items ?? [], [stableSessionsPayload]);
  const sessionsUnavailable = stableSessionsPayload?.unavailable ?? false;
  const selectedSessionSummary = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessions]
  );
  const selectedSessionBotId = useMemo(
    () => normalizeSelectedBotId(selectedSessionSummary?.bot_id, availableBotIds),
    [availableBotIds, selectedSessionSummary?.bot_id],
  );
  const detailBotId = selectedSessionBotId ?? activeBotId;

  const detailQueryBaseKey = useMemo(
    () =>
      queryKeys.dashboard.sessionDetail(
        detailBotId ?? "",
        selectedSessionId ?? "",
      ),
    [detailBotId, selectedSessionId],
  );
  const detailQueryKey = useMemo(
    () => [...detailQueryBaseKey, "latest", SESSION_THREAD_PAGE_SIZE] as const,
    [detailQueryBaseKey],
  );

  const handleSessionStreamEvent = useCallback(
    (event: SessionStreamEvent) => {
      const invalidating = new Set([
        "task_started",
        "task_progress",
        "task_complete",
        "task_failed",
        "tool_call_end",
        "artifact_ready",
        "approval_required",
        "approval_resolved",
        "session_completed",
      ]);
      if (!invalidating.has(event.type)) return;
      void queryClient.invalidateQueries({ queryKey: detailQueryBaseKey });
      void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
    },
    [queryClient, detailQueryBaseKey, sessionsQueryKey],
  );

  const streamSessionId =
    selectedSessionId && selectedSessionId !== NEW_SESSION_PLACEHOLDER_ID
      ? selectedSessionId
      : null;
  const { connected: streamConnected } = useSessionStream({
    agentId: detailBotId ?? null,
    sessionId: streamSessionId,
    enabled: Boolean(detailBotId && streamSessionId),
    onEvent: handleSessionStreamEvent,
  });

  const detailQuery = useControlPlaneQuery<SessionDetail>({
    tier: "realtime",
    queryKey: detailQueryKey,
    enabled: Boolean(detailBotId && selectedSessionId),
    refetchInterval: streamConnected
      ? false
      : pendingRequest
        ? 2_000
        : 15_000,
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: async ({ signal }) => {
      if (!detailBotId || !selectedSessionId) {
        throw new Error(t("sessions.noSelection"));
      }
      return fetchControlPlaneDashboardJson<SessionDetail>(
        `/agents/${detailBotId}/sessions/${encodeURIComponent(selectedSessionId)}`,
        {
          signal,
          params: {
            limit: SESSION_THREAD_PAGE_SIZE,
          },
          fallbackError: t("sessions.loadError"),
        },
      );
    },
  });

  const stableDetailPayload = useContentStable(detailQuery.data);
  const activeDetail =
    stableDetailPayload?.summary.session_id === selectedSessionId ? stableDetailPayload : null;
  const loadedHistoryMessages = useMemo(
    () => mergeSessionHistoryPages(activeDetail, olderDetailPages),
    [activeDetail, olderDetailPages],
  );
  const selectedSummary = activeDetail?.summary ?? selectedSessionSummary;
  const effectiveBotId =
    normalizeSelectedBotId(selectedSummary?.bot_id, availableBotIds) ?? activeBotId;
  const oldestLoadedPage = olderDetailPages[olderDetailPages.length - 1] ?? activeDetail;
  const hasOlderMessages = oldestLoadedPage?.page?.has_more ?? false;
  const nextHistoryCursor = oldestLoadedPage?.page?.next_cursor ?? null;

  useEffect(() => {
    setOlderDetailPages([]);
    setLoadingOlderDetailPages(false);
  }, [detailBotId, selectedSessionId]);

  useEffect(() => {
    if (!pendingRequest || !activeDetail) return;
    if (activeDetail.summary.session_id !== pendingRequest.sessionId) return;

    const mirroredOnServer = activeDetail.messages.some(
      (message) =>
        message.role === "user" && message.text.trim() === pendingRequest.text.trim()
    );

    if (!mirroredOnServer) return;

    setPendingMessages((current) =>
      current.filter((message) => message.requestId !== pendingRequest.requestId)
    );
    setPendingRequest(null);
    void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
  }, [activeDetail, pendingRequest, queryClient, sessionsQueryKey]);

  useEffect(() => {
    if (sessionsQuery.isLoading) return;
    if (isNewChatMode) return;
    if (!selectedSessionId && sessions.length > 0 && isDesktop) {
      setSelectedSessionId(sessions[0].session_id);
    }
  }, [isDesktop, isNewChatMode, selectedSessionId, sessions, sessionsQuery.isLoading]);

  const visiblePendingMessages = useMemo(() => {
    const targetSessionId = selectedSessionId ?? NEW_SESSION_PLACEHOLDER_ID;
    return pendingMessages.filter((message) => message.session_id === targetSessionId);
  }, [pendingMessages, selectedSessionId]);

  const resetThreadState = useCallback(() => {
    setDraft("");
    setComposerError(null);
    setPendingRequest(null);
    setPendingMessages([]);
    setOlderDetailPages([]);
    setLoadingOlderDetailPages(false);
    queryClient.removeQueries({ queryKey: detailQueryBaseKey });
  }, [detailQueryBaseKey, queryClient]);

  const loadOlderMessages = useCallback(async () => {
    if (!detailBotId || !selectedSessionId || !activeDetail || loadingOlderDetailPages) {
      return;
    }
    if (!hasOlderMessages || !nextHistoryCursor) {
      return;
    }

    setLoadingOlderDetailPages(true);
    try {
      const page = await fetchControlPlaneDashboardJson<SessionDetail>(
        `/agents/${detailBotId}/sessions/${encodeURIComponent(selectedSessionId)}`,
        {
          params: {
            limit: SESSION_THREAD_PAGE_SIZE,
            before: nextHistoryCursor,
          },
          fallbackError: t("sessions.loadError"),
        },
      );
      setOlderDetailPages((current) => [...current, page]);
    } finally {
      setLoadingOlderDetailPages(false);
    }
  }, [
    activeDetail,
    detailBotId,
    hasOlderMessages,
    loadingOlderDetailPages,
    nextHistoryCursor,
    selectedSessionId,
    t,
  ]);

  const handleAgentChange = useCallback(
    (agentId: string | undefined) => {
      const hasSelectedSession = Boolean(selectedSessionId);
      const canPreserveSelection =
        hasSelectedSession &&
        (!agentId ||
          normalizeSelectedBotId(selectedSummary?.bot_id, availableBotIds) ===
            normalizeSelectedBotId(agentId, availableBotIds));

      setActiveBotId(normalizeSelectedBotId(agentId, availableBotIds));
      setComposerError(null);
      setContextDrawerOpen(false);

      if (!hasSelectedSession) return;

      setIsNewChatMode(false);

      if (canPreserveSelection) return;

      setSelectedSessionId(null);
      resetThreadState();
    },
    [availableBotIds, resetThreadState, selectedSessionId, selectedSummary?.bot_id]
  );

  const handleSelectSession = useCallback(
    (session: SessionSummary) => {
      setActiveBotId(
        normalizeSelectedBotId(session.bot_id, availableBotIds) ?? session.bot_id
      );
      setSelectedSessionId(session.session_id);
      setIsNewChatMode(false);
      setComposerError(null);
      setPendingRequest(null);
      setPendingMessages((current) =>
        current.filter((message) => message.session_id === session.session_id)
      );
      if (!isDesktop) {
        setMobileRailOpen(false);
      }
    },
    [availableBotIds, isDesktop]
  );

  const handleNewChat = useCallback(() => {
    setActiveBotId((current) => {
      const candidate = selectedSummary?.bot_id ?? current;
      return normalizeSelectedBotId(candidate, availableBotIds) ?? current;
    });
    setSelectedSessionId(null);
    setIsNewChatMode(true);
    setContextDrawerOpen(false);
    resetThreadState();
    if (!isDesktop) {
      setMobileRailOpen(false);
    }
  }, [availableBotIds, isDesktop, resetThreadState, selectedSummary?.bot_id]);

  const sendMessage = useCallback(
    async (text: string, options?: { requestId?: string; sessionId?: string | null }) => {
      const trimmedText = text.trim();
      const sendBotId = effectiveBotId;
      if (!trimmedText || !sendBotId || composerSubmitting) return;

      const requestId =
        options?.requestId ??
        globalThis.crypto?.randomUUID?.() ??
        `session-send-${Date.now()}`;
      const draftSessionId = options?.sessionId ?? selectedSessionId ?? null;
      const optimisticSessionId = draftSessionId ?? NEW_SESSION_PLACEHOLDER_ID;
      const timestamp = new Date().toISOString();

      setComposerSubmitting(true);
      setComposerError(null);
      setPendingRequest(null);
      setPendingMessages((current) => {
        const filtered = current.filter((message) => message.requestId !== requestId);
        return [
          ...filtered,
          {
            id: `${requestId}:user`,
            requestId,
            role: "user",
            text: trimmedText,
            timestamp,
            model: null,
            cost_usd: null,
            query_id: -1,
            session_id: optimisticSessionId,
            error: false,
            clientState: "pending",
            retryText: trimmedText,
          },
          {
            id: `${requestId}:assistant`,
            requestId,
            role: "assistant",
            text: "",
            timestamp,
            model: null,
            cost_usd: null,
            query_id: -1,
            session_id: optimisticSessionId,
            error: false,
            clientState: "pending",
            placeholderKind: "assistant",
          },
        ];
      });

      try {
        const response = await mutateControlPlaneDashboardJson<SessionSendResponse>(
          `/agents/${sendBotId}/sessions/messages`,
          {
            fallbackError: t("sessions.sendUnavailable"),
            body: {
              text: trimmedText,
              session_id: draftSessionId,
            } satisfies SessionSendRequest,
          }
        );
        const resolvedSessionId = response.session_id;
        setPendingMessages((current) =>
          current.map((message) =>
            message.requestId === requestId
              ? { ...message, session_id: resolvedSessionId }
              : message
          )
        );
        setPendingRequest({
          requestId,
          text: trimmedText,
          sessionId: resolvedSessionId,
          agentId: sendBotId,
          startedAt: Date.now(),
        });
        setSelectedSessionId(resolvedSessionId);
        setIsNewChatMode(false);
        setDraft("");
        if (!draftSessionId) {
          queryClient.removeQueries({ queryKey: detailQueryKey });
        }
        void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
      } catch (error) {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message
            : t("sessions.sendUnavailable");
        setComposerError(message);
        setPendingMessages((current) =>
          current.flatMap((item) => {
            if (item.requestId !== requestId) return [item];
            if (item.role === "assistant") return [];
            return [{ ...item, clientState: "failed" }];
          })
        );
      } finally {
        setComposerSubmitting(false);
      }
    },
    [effectiveBotId, composerSubmitting, detailQueryKey, queryClient, selectedSessionId, sessionsQueryKey, t]
  );

  const handleRetryPendingMessage = useCallback(
    (requestId: string) => {
      const failedMessage = pendingMessages.find(
        (message) =>
          message.requestId === requestId &&
          message.role === "user" &&
          message.clientState === "failed"
      );
      if (!failedMessage?.retryText) return;
      void sendMessage(failedMessage.retryText, {
        requestId,
        sessionId:
          failedMessage.session_id === NEW_SESSION_PLACEHOLDER_ID
            ? null
            : failedMessage.session_id,
      });
    },
    [pendingMessages, sendMessage]
  );

  const mobileRailPresence = useAnimatedPresence(!isDesktop && mobileRailOpen, null, {
    duration: 220,
  });
  useBodyScrollLock(mobileRailPresence.shouldRender);
  useEscapeToClose(mobileRailPresence.shouldRender, () => setMobileRailOpen(false));

  const composerDisabled = !effectiveBotId;
  const showThinking = Boolean(
    pendingRequest ||
      (selectedSummary?.running_count && selectedSummary.running_count > 0) ||
      (selectedSummary?.latest_status === "running" || selectedSummary?.latest_status === "retrying"),
  );

  const resolvedTitle = selectedSummary
    ? resolveSessionTitle(selectedSummary)
    : isNewChatMode
      ? t("chat.thread.empty", { defaultValue: "Start a conversation" })
      : t("chat.thread.empty", { defaultValue: "Start a conversation" });

  const effectiveAgentLabel = useMemo(() => {
    if (!effectiveBotId) return null;
    const agent = agents.find((entry) => entry.id === effectiveBotId);
    return agent?.label ?? effectiveBotId;
  }, [agents, effectiveBotId]);

  const modelLabel = useMemo(() => {
    if (!activeDetail) return null;
    for (let index = activeDetail.messages.length - 1; index >= 0; index -= 1) {
      const message = activeDetail.messages[index];
      const model = message.model?.trim() || message.linked_execution?.model?.trim() || null;
      if (model) return model;
    }
    return null;
  }, [activeDetail]);

  const tourVariant =
    sessionsQuery.error?.message || sessionsUnavailable
      ? "unavailable"
      : sessionsQuery.isLoading && sessions.length === 0
        ? "loading"
        : sessions.length === 0
          ? "empty"
          : "default";

  return (
    <div
      className="animate-in flex h-full min-h-0 overflow-hidden bg-[var(--canvas)] text-[var(--text-primary)]"
      {...tourRoute("sessions", tourVariant)}
    >
      <div className="hidden md:flex" {...tourAnchor("sessions.conversation-rail")}>
        <SessionRail
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          search={search}
          onSearchChange={setSearch}
          loading={sessionsQuery.isLoading}
          error={sessionsQuery.error?.message ?? null}
          unavailable={sessionsUnavailable}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col" {...tourAnchor("sessions.thread")}>
        <ChatHeader
          title={resolvedTitle}
          agentId={effectiveBotId ?? null}
          sessionId={streamSessionId}
          onOpenRail={() => setMobileRailOpen(true)}
          onOpenContext={Boolean(selectedSummary) ? () => setContextDrawerOpen(true) : undefined}
          showRailToggle
          showContextToggle={Boolean(selectedSummary)}
          scrolled={threadScrolled}
          sessionActive={Boolean(
            selectedSummary &&
              (selectedSummary.latest_status === "running" ||
                selectedSummary.latest_status === "retrying" ||
                selectedSummary.latest_status === "queued"),
          )}
          sessionPaused={selectedSummary?.latest_status === "paused"}
        />
        <ChatThread
          messages={loadedHistoryMessages}
          pendingMessages={visiblePendingMessages}
          orphanExecutions={activeDetail?.orphan_executions ?? []}
          showThinking={showThinking}
          loading={Boolean(selectedSessionId && detailQuery.isLoading && !activeDetail)}
          error={detailQuery.error?.message ?? null}
          agentLabel={effectiveAgentLabel}
          onRetryPending={handleRetryPendingMessage}
          onLoadOlder={loadOlderMessages}
          hasOlder={hasOlderMessages}
          loadingOlder={loadingOlderDetailPages}
          onScrollStateChange={setThreadScrolled}
          agentId={effectiveBotId ?? null}
          sessionId={streamSessionId}
          footer={
            <div {...tourAnchor("sessions.composer")}>
              <ChatComposer
                value={draft}
                onChange={(value) => {
                  setDraft(value);
                  if (composerError) setComposerError(null);
                }}
                onSubmit={() => void sendMessage(draft)}
                agentId={effectiveBotId ?? null}
                onAgentChange={handleAgentChange}
                lockedAgent={Boolean(selectedSessionId && effectiveBotId)}
                modelLabel={modelLabel}
                disabled={composerDisabled}
                busy={composerSubmitting}
                helper={
                  composerDisabled
                    ? t("sessions.composer.selectAgentToStart", {
                        defaultValue: "Select a specific agent to start a chat.",
                      })
                    : null
                }
                error={composerError}
              />
            </div>
          }
        />
      </div>

      <SessionContextDrawer
        open={contextDrawerOpen}
        onOpenChange={setContextDrawerOpen}
        detail={activeDetail}
        summary={selectedSummary}
      />

      {mobileRailPresence.shouldRender ? (
        <>
          <button
            type="button"
            aria-label={t("chat.rail.close", { defaultValue: "Close" })}
            onClick={() => setMobileRailOpen(false)}
            className={cn(
              "fixed inset-0 z-[48] cursor-default border-0 bg-[color:var(--overlay-backdrop-bg)] backdrop-blur-[6px] transition-opacity md:hidden",
              mobileRailPresence.isVisible ? "opacity-100" : "pointer-events-none opacity-0",
            )}
          />
          <div
            className={cn(
              "fixed inset-y-0 left-0 z-[49] w-[min(320px,calc(100vw-48px))] overflow-hidden shadow-[var(--shadow-floating)] transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.22,1,0.36,1)] md:hidden",
              mobileRailPresence.isVisible
                ? "translate-x-0 opacity-100"
                : "pointer-events-none -translate-x-2 opacity-0",
            )}
            role="dialog"
            aria-modal="true"
            aria-label={t("chat.rail.title", { defaultValue: "Conversations" })}
          >
            <SessionRail
              sessions={sessions}
              selectedSessionId={selectedSessionId}
              onSelectSession={handleSelectSession}
              onNewChat={handleNewChat}
              search={search}
              onSearchChange={setSearch}
              loading={sessionsQuery.isLoading}
              error={sessionsQuery.error?.message ?? null}
              unavailable={sessionsUnavailable}
              onClose={() => setMobileRailOpen(false)}
              className="border-r-0"
            />
          </div>
        </>
      ) : null}
    </div>
  );
}

export default function SessionsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full min-h-0 overflow-hidden bg-[var(--canvas)]">
          <div className="hidden h-full w-72 shrink-0 border-r border-[var(--border-subtle)] bg-[var(--shell)] md:block">
            <div className="h-14 border-b border-[var(--divider-hair)]" />
            <div className="p-2">
              <div className="h-9 w-full animate-pulse rounded-[var(--radius-input)] bg-[var(--panel-soft)]" />
            </div>
            <div className="flex flex-col gap-1 p-2">
              {Array.from({ length: 8 }).map((_, index) => (
                <div
                  key={index}
                  className="h-[44px] w-full animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]"
                />
              ))}
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="h-12 border-b border-[var(--divider-hair)]" />
            <div className="mx-auto flex w-full max-w-[720px] flex-col gap-6 px-6 py-8">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="h-20 w-full animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]"
                />
              ))}
            </div>
          </div>
        </div>
      }
    >
      <SessionsPageContent />
    </Suspense>
  );
}
