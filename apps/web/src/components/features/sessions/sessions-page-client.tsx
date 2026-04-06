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
import { useQueryClient } from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { SessionChatComposer } from "@/components/sessions/session-chat-composer";
import { SessionContextPanel } from "@/components/sessions/session-context-panel";
import { SessionConversationRail } from "@/components/sessions/session-conversation-rail";
import {
  SessionThreadView,
  type PendingSessionMessage,
} from "@/components/sessions/session-thread-view";
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
import { cn } from "@/lib/utils";

const SESSION_FETCH_LIMIT = 200;
const SESSION_THREAD_PAGE_SIZE = 24;
const MIN_VISIBLE_FRAGMENT_EXECUTIONS = 3;
const NEW_SESSION_PLACEHOLDER_ID = "__new_session__";

function normalizeSelectedBotId(
  candidate: string | null | undefined,
  availableBotIds: string[],
) {
  if (!candidate) return undefined;
  const match = availableBotIds.find((botId) => botId.toLowerCase() === candidate.toLowerCase());
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

function shouldSurfaceSessionInRail(session: SessionSummary) {
  if (session.query_count > 0) return true;
  if (session.running_count > 0) return true;
  if (session.failed_count > 0) return true;
  if (session.execution_count >= MIN_VISIBLE_FRAGMENT_EXECUTIONS) return true;
  if (session.latest_response_preview?.trim()) return true;
  if (session.name?.trim()) return true;
  return false;
}

function SessionsPageContent() {
  const { t } = useAppI18n();
  const { currentStep, status } = useAppTour();
  const { bots } = useBotCatalog();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isDesktop = useMediaQuery("(min-width: 1080px)");
  const showDesktopContextPanel = useMediaQuery("(min-width: 1380px)");
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const queryBotId = searchParams.get("bot");

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
  const [mobileContextOpen, setMobileContextOpen] = useState(false);
  const [pendingMessages, setPendingMessages] = useState<PendingSessionMessage[]>([]);
  const [olderDetailPages, setOlderDetailPages] = useState<SessionDetail[]>([]);
  const [loadingOlderDetailPages, setLoadingOlderDetailPages] = useState(false);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [pendingRequest, setPendingRequest] = useState<{
    requestId: string;
    text: string;
    sessionId: string;
    botId: string;
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
    if (showDesktopContextPanel) {
      setMobileContextOpen(false);
    }
  }, [isDesktop, showDesktopContextPanel]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.innerWidth >= 1024) return;
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
      params.set("bot", activeBotId);
    } else {
      params.delete("bot");
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

  const sessions = useMemo(() => sessionsQuery.data?.items ?? [], [sessionsQuery.data]);
  const sessionsUnavailable = sessionsQuery.data?.unavailable ?? false;
  const visibleSessions = useMemo(() => {
    if (search.trim()) {
      return sessions;
    }

    const meaningful = sessions.filter(shouldSurfaceSessionInRail);

    if (selectedSessionId) {
      const selected = sessions.find((session) => session.session_id === selectedSessionId);
      const remainder = meaningful.filter(
        (session) => session.session_id !== selectedSessionId,
      );

      if (selected && !shouldSurfaceSessionInRail(selected)) {
        return [selected, ...remainder.slice(0, 2)];
      }
    }

    if (meaningful.length > 0) {
      return meaningful.slice(0, 3);
    }

    return sessions.slice(0, Math.min(3, sessions.length));
  }, [search, selectedSessionId, sessions]);
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

  const detailQuery = useControlPlaneQuery<SessionDetail>({
    tier: "realtime",
    queryKey: detailQueryKey,
    enabled: Boolean(detailBotId && selectedSessionId),
    refetchInterval: pendingRequest ? 2_000 : 15_000,
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

  const activeDetail =
    detailQuery.data?.summary.session_id === selectedSessionId ? detailQuery.data : null;
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
    if (!selectedSessionId) {
      setLoadingSessionId(null);
      return;
    }

    if (activeDetail?.summary.session_id === selectedSessionId || detailQuery.error) {
      setLoadingSessionId((current) =>
        current === selectedSessionId ? null : current,
      );
    }
  }, [activeDetail?.summary.session_id, detailQuery.error, selectedSessionId]);

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
    if (!selectedSessionId) {
      if (isDesktop && visibleSessions.length > 0) {
        setSelectedSessionId(visibleSessions[0]?.session_id ?? null);
      }
      return;
    }
    if (visibleSessions.some((session) => session.session_id === selectedSessionId)) {
      return;
    }
    if (pendingRequest?.sessionId === selectedSessionId) {
      return;
    }
    if (isDesktop && visibleSessions.length > 0) {
      setSelectedSessionId(visibleSessions[0]?.session_id ?? null);
    }
  }, [
    isDesktop,
    isNewChatMode,
    pendingRequest?.sessionId,
    selectedSessionId,
    visibleSessions,
    sessionsQuery.isLoading,
  ]);

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

  const handleBotChange = useCallback(
    (botId: string | undefined) => {
      const hasSelectedSession = Boolean(selectedSessionId);
      const canPreserveSelection =
        hasSelectedSession &&
        (!botId ||
          normalizeSelectedBotId(selectedSummary?.bot_id, availableBotIds) ===
            normalizeSelectedBotId(botId, availableBotIds));

      setActiveBotId(normalizeSelectedBotId(botId, availableBotIds));
      setMobileContextOpen(false);
      setComposerError(null);

      if (!hasSelectedSession) {
        return;
      }

      setIsNewChatMode(false);

      if (canPreserveSelection) {
        return;
      }

      setSelectedSessionId(null);
      resetThreadState();
    },
    [availableBotIds, resetThreadState, selectedSessionId, selectedSummary?.bot_id]
  );

  const handleSelectSession = useCallback(
    (session: SessionSummary) => {
      if (session.session_id !== selectedSessionId) {
        setLoadingSessionId(session.session_id);
      }
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
    [availableBotIds, isDesktop, selectedSessionId]
  );

  const handleNewChat = useCallback(() => {
    setActiveBotId((current) => {
      const candidate = selectedSummary?.bot_id ?? current;
      return normalizeSelectedBotId(candidate, availableBotIds) ?? current;
    });
    setLoadingSessionId(null);
    setSelectedSessionId(null);
    setIsNewChatMode(true);
    setMobileContextOpen(false);
    resetThreadState();
    if (!isDesktop) {
      setMobileRailOpen(false);
    }
  }, [availableBotIds, isDesktop, resetThreadState, selectedSummary?.bot_id]);

  const sendMessage = useCallback(
    async (
      text: string,
      options?: {
        requestId?: string;
        sessionId?: string | null;
      }
    ) => {
      const trimmedText = text.trim();
      const sendBotId = effectiveBotId;
      if (!trimmedText || !sendBotId || composerSubmitting) return;

      const requestId = options?.requestId ?? globalThis.crypto?.randomUUID?.() ?? `session-send-${Date.now()}`;
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
          botId: sendBotId,
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

  const sessionTransitioning = Boolean(
    selectedSessionId &&
      loadingSessionId === selectedSessionId &&
      activeDetail?.summary.session_id !== selectedSessionId
  );

  const mobileRailPresence = useAnimatedPresence(!isDesktop && mobileRailOpen, null, {
    duration: 220,
  });
  const mobileContextPresence = useAnimatedPresence(
    !showDesktopContextPanel && mobileContextOpen,
    null,
    { duration: 220 }
  );
  useBodyScrollLock(mobileRailPresence.shouldRender || mobileContextPresence.shouldRender);
  useEscapeToClose(mobileRailPresence.shouldRender, () => setMobileRailOpen(false));
  useEscapeToClose(mobileContextPresence.shouldRender, () => setMobileContextOpen(false));

  const composerDisabled = !effectiveBotId || sessionTransitioning;
  const composerPlaceholder = sessionTransitioning
    ? t("sessions.thread.loadingConversation", {
        defaultValue: "Loading conversation...",
      })
    : composerDisabled
    ? t("sessions.composer.selectBotToStart", {
        defaultValue: "Select a specific bot here to start a chat.",
      })
    : t("sessions.composer.enabledPlaceholder");
  const composerHelper = sessionTransitioning
    ? t("sessions.thread.loadingConversation", {
        defaultValue: "Loading conversation...",
      })
    : composerDisabled
    ? t("sessions.thread.noBotDescription", {
        defaultValue: "Choose a specific bot in the composer to start a new chat.",
      })
    : pendingRequest
      ? t("sessions.thread.waitingForReply", {
          defaultValue: "Waiting for the bot reply...",
        })
      : selectedSessionId
        ? t("sessions.thread.continueConversation", {
            defaultValue: "Continue the current conversation.",
          })
        : t("sessions.thread.startConversationDescription", {
            defaultValue: "Start a new conversation with the selected bot.",
          });

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
      className="animate-in flex h-full min-h-0 overflow-hidden bg-[var(--surface-canvas)] text-[var(--text-primary)]"
      {...tourRoute("sessions", tourVariant)}
    >
      <div className="hidden h-full min-h-0 w-[22rem] shrink-0 lg:block xl:w-[23rem]" {...tourAnchor("sessions.conversation-rail")}>
        <SessionConversationRail
          search={search}
          onSearchChange={setSearch}
          sessions={visibleSessions}
          selectedSessionId={selectedSessionId}
          loading={sessionsQuery.isLoading}
          refreshing={sessionsQuery.isFetching && !sessionsQuery.isLoading}
          loadingSessionId={loadingSessionId}
          error={sessionsQuery.error?.message}
          unavailable={sessionsUnavailable}
          onRefresh={() => {
            void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
          }}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
        />
      </div>

      <div
        className={cn(
          "grid min-h-0 flex-1",
          showDesktopContextPanel
            ? "grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_23.5rem]"
            : "grid-cols-1"
        )}
      >
        <div className="min-h-0 min-w-0" {...tourAnchor("sessions.thread")}>
          <SessionThreadView
            botId={effectiveBotId}
            hasSelectedSession={Boolean(selectedSessionId)}
            detail={activeDetail}
            summary={selectedSummary}
            historyMessages={loadedHistoryMessages}
            pendingMessages={visiblePendingMessages}
            loading={Boolean(selectedSessionId && detailQuery.isLoading && !activeDetail)}
            transitioning={sessionTransitioning}
            loadingOlderHistory={loadingOlderDetailPages}
            hasOlderHistory={hasOlderMessages}
            onLoadOlderHistory={loadOlderMessages}
            error={detailQuery.error?.message ?? null}
            showRailToggle={!isDesktop}
            onOpenRail={() => setMobileRailOpen(true)}
            showContextToggle={Boolean(selectedSummary)}
            onOpenContext={() => setMobileContextOpen(true)}
            onRetryPendingMessage={handleRetryPendingMessage}
            footer={
              <div {...tourAnchor("sessions.composer")}>
                <SessionChatComposer
                  botId={effectiveBotId}
                  onBotChange={handleBotChange}
                  lockedBot={Boolean(selectedSessionId && effectiveBotId)}
                  value={draft}
                  onChange={(value) => {
                    setDraft(value);
                    if (composerError) {
                      setComposerError(null);
                    }
                  }}
                  onSubmit={() => void sendMessage(draft)}
                  submitting={composerSubmitting}
                  disabled={composerDisabled}
                  helperText={composerHelper}
                  error={composerError}
                  placeholder={composerPlaceholder}
                />
              </div>
            }
          />
        </div>

        {showDesktopContextPanel ? (
          <div {...tourAnchor("sessions.context-panel")}>
            <SessionContextPanel detail={activeDetail} summary={selectedSummary} />
          </div>
        ) : null}
      </div>

      {mobileRailPresence.shouldRender ? (
        <>
          <div
            className={cn(
              "app-overlay-backdrop z-[48] transition-opacity duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] lg:hidden",
              mobileRailPresence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
            )}
            onClick={() => setMobileRailOpen(false)}
          />
          <div
            className={cn(
              "fixed inset-y-0 left-0 z-[49] w-[min(24rem,calc(100vw-1rem))] overflow-hidden border-r border-[var(--border-subtle)] bg-[var(--surface-canvas)] shadow-[0_28px_90px_rgba(0,0,0,0.18)] transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] lg:hidden",
              mobileRailPresence.isVisible
                ? "translate-x-0 opacity-100"
                : "pointer-events-none -translate-x-4 opacity-0"
            )}
            role="dialog"
            aria-modal="true"
            aria-label={t("sessions.page.botConversations")}
          >
            <SessionConversationRail
              search={search}
              onSearchChange={setSearch}
              sessions={visibleSessions}
              selectedSessionId={selectedSessionId}
              loading={sessionsQuery.isLoading}
              refreshing={sessionsQuery.isFetching && !sessionsQuery.isLoading}
              loadingSessionId={loadingSessionId}
              error={sessionsQuery.error?.message}
              unavailable={sessionsUnavailable}
              onRefresh={() => {
                void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
              }}
              onSelectSession={handleSelectSession}
              onNewChat={handleNewChat}
              onClose={() => setMobileRailOpen(false)}
              className="border-r-0"
            />
          </div>
        </>
      ) : null}

      {mobileContextPresence.shouldRender ? (
        <>
          <div
            className={cn(
              "app-overlay-backdrop z-[48] transition-opacity duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] xl:hidden",
              mobileContextPresence.isVisible ? "opacity-100" : "pointer-events-none opacity-0"
            )}
            onClick={() => setMobileContextOpen(false)}
          />
          <div
            className={cn(
              "fixed inset-y-0 right-0 z-[49] w-[min(23rem,calc(100vw-1rem))] overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--surface-canvas)] shadow-[0_28px_90px_rgba(0,0,0,0.18)] transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] xl:hidden",
              mobileContextPresence.isVisible
                ? "translate-x-0 opacity-100"
                : "pointer-events-none translate-x-4 opacity-0"
            )}
            role="dialog"
            aria-modal="true"
            aria-label={t("sessions.page.conversationInfo", { defaultValue: "Conversation info" })}
          >
            <SessionContextPanel detail={activeDetail} summary={selectedSummary} />
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
        <div className="flex h-full min-h-0 overflow-hidden bg-[var(--surface-canvas)]">
          <div className="hidden h-full w-[22rem] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface-canvas)] lg:block">
            <div className="space-y-3 px-4 py-4">
              <div className="skeleton h-4 w-28 rounded-xl" />
              <div className="skeleton h-12 w-full rounded-[1rem]" />
              <div className="skeleton h-12 w-full rounded-[1rem]" />
              <div className="skeleton h-11 w-full rounded-[1rem]" />
              {Array.from({ length: 7 }).map((_, index) => (
                <div key={index} className="skeleton h-[78px] w-full rounded-[1rem]" />
              ))}
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="border-b border-[var(--border-subtle)] px-4 py-4 sm:px-6">
              <div className="flex items-center gap-3">
                <div className="skeleton-circle h-11 w-11" />
                <div className="space-y-2">
                  <div className="skeleton h-4 w-44 rounded-xl" />
                  <div className="skeleton h-3 w-28 rounded-xl" />
                </div>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden px-4 py-5 sm:px-6">
              <div className="mx-auto max-w-[52rem] space-y-4">
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
            </div>
            <div className="border-t border-[var(--border-subtle)] px-4 py-4 sm:px-6">
              <div className="mx-auto max-w-[52rem] rounded-[1.5rem] border border-[var(--border-subtle)] p-4">
                <div className="skeleton h-[54px] w-full rounded-[1rem]" />
              </div>
            </div>
          </div>
        </div>
      }
    >
      <SessionsPageContent />
    </Suspense>
  );
}
