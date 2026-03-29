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
import { useAsyncResource } from "@/hooks/use-async-resource";
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
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import type {
  SessionDetail,
  SessionSendRequest,
  SessionSendResponse,
  SessionSummary,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const SESSION_FETCH_LIMIT = 200;
const NEW_SESSION_PLACEHOLDER_ID = "__new_session__";

function normalizeSelectedBotId(
  candidate: string | null | undefined,
  availableBotIds: string[],
) {
  if (!candidate) return undefined;
  return availableBotIds.includes(candidate) ? candidate : undefined;
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
  const [pendingRequest, setPendingRequest] = useState<{
    requestId: string;
    text: string;
    sessionId: string;
    botId: string;
    startedAt: number;
  } | null>(null);

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

  const sessionsResource = useAsyncResource<{
    items: SessionSummary[];
    unavailable: boolean;
  }>({
    enabled: availableBotIds.length > 0,
    pollIntervalMs: availableBotIds.length > 0 ? 8_000 : null,
    fetcher: async (signal) => {
      const response = await fetchControlPlaneDashboardJsonAllowError<SessionSummary[]>(
        activeBotId ? `/agents/${activeBotId}/sessions` : "/sessions",
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
        unavailable: activeBotId ? !response.ok : false,
      };
    },
  });

  const sessions = useMemo(() => sessionsResource.data?.items ?? [], [sessionsResource.data]);
  const sessionsUnavailable = sessionsResource.data?.unavailable ?? false;
  const selectedSessionSummary = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessions]
  );
  const detailBotId = selectedSessionSummary?.bot_id ?? activeBotId;

  const detailResource = useAsyncResource<SessionDetail>({
    enabled: Boolean(detailBotId && selectedSessionId),
    pollIntervalMs: detailBotId && selectedSessionId ? 8_000 : null,
    fetcher: async (signal) => {
      if (!detailBotId || !selectedSessionId) {
        throw new Error(t("sessions.noSelection"));
      }
      return fetchControlPlaneDashboardJson<SessionDetail>(
        `/agents/${detailBotId}/sessions/${encodeURIComponent(selectedSessionId)}`,
        {
          signal,
          fallbackError: t("sessions.loadError"),
        }
      );
    },
  });

  const activeDetail =
    detailResource.data?.summary.session_id === selectedSessionId ? detailResource.data : null;
  const selectedSummary = activeDetail?.summary ?? selectedSessionSummary;
  const effectiveBotId = selectedSummary?.bot_id ?? activeBotId;

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
    void sessionsResource.refresh({ background: true, preserveError: true });
  }, [activeDetail, pendingRequest, sessionsResource]);

  useEffect(() => {
    if (!pendingRequest || !detailBotId || !selectedSessionId) return;
    let disposed = false;

    const poll = async () => {
      const response = await detailResource.refresh({ background: true, preserveError: true });
      if (disposed || !response) return;
      void sessionsResource.refresh({ background: true, preserveError: true });
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 1600);

    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [detailBotId, detailResource, pendingRequest, selectedSessionId, sessionsResource]);

  useEffect(() => {
    if (sessionsResource.initialLoading) return;
    if (isNewChatMode) return;
    if (!selectedSessionId) {
      if (isDesktop && sessions.length > 0) {
        setSelectedSessionId(sessions[0]?.session_id ?? null);
      }
      return;
    }
    if (sessions.some((session) => session.session_id === selectedSessionId)) {
      return;
    }
    if (pendingRequest?.sessionId === selectedSessionId) {
      return;
    }
    if (isDesktop && sessions.length > 0) {
      setSelectedSessionId(sessions[0]?.session_id ?? null);
    }
  }, [
    isDesktop,
    isNewChatMode,
    pendingRequest?.sessionId,
    selectedSessionId,
    sessions,
    sessionsResource.initialLoading,
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
    detailResource.setData(null);
  }, [detailResource]);

  const handleBotChange = useCallback(
    (botId: string | undefined) => {
      const hasSelectedSession = Boolean(selectedSessionId);
      const canPreserveSelection =
        hasSelectedSession && (!botId || selectedSummary?.bot_id === botId);

      setActiveBotId(botId);
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
    [resetThreadState, selectedSessionId, selectedSummary?.bot_id]
  );

  const handleSelectSession = useCallback(
    (session: SessionSummary) => {
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
    [isDesktop]
  );

  const handleNewChat = useCallback(() => {
    setSelectedSessionId(null);
    setIsNewChatMode(true);
    setMobileContextOpen(false);
    resetThreadState();
    if (!isDesktop) {
      setMobileRailOpen(false);
    }
  }, [isDesktop, resetThreadState]);

  const sendMessage = useCallback(
    async (
      text: string,
      options?: {
        requestId?: string;
        sessionId?: string | null;
      }
    ) => {
      const trimmedText = text.trim();
      if (!trimmedText || !activeBotId || composerSubmitting) return;

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
          `/agents/${activeBotId}/sessions/messages`,
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
          botId: activeBotId,
          startedAt: Date.now(),
        });
        setSelectedSessionId(resolvedSessionId);
        setIsNewChatMode(false);
        setDraft("");
        if (!draftSessionId) {
          detailResource.setData(null);
        }
        void sessionsResource.refresh({ background: true, preserveError: true });
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
    [activeBotId, composerSubmitting, detailResource, selectedSessionId, sessionsResource, t]
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
  const mobileContextPresence = useAnimatedPresence(
    !showDesktopContextPanel && mobileContextOpen,
    null,
    { duration: 220 }
  );
  useBodyScrollLock(mobileRailPresence.shouldRender || mobileContextPresence.shouldRender);
  useEscapeToClose(mobileRailPresence.shouldRender, () => setMobileRailOpen(false));
  useEscapeToClose(mobileContextPresence.shouldRender, () => setMobileContextOpen(false));

  const composerDisabled = !activeBotId;
  const composerPlaceholder = composerDisabled
    ? t("sessions.composer.selectBotToStart", {
        defaultValue: "Select a specific bot here to start a chat.",
      })
    : t("sessions.composer.enabledPlaceholder");
  const composerHelper = composerDisabled
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
    sessionsResource.error || sessionsUnavailable
      ? "unavailable"
      : sessionsResource.initialLoading && sessions.length === 0
        ? "loading"
        : sessions.length === 0
          ? "empty"
          : "default";

  return (
    <div className="animate-in flex h-full min-h-0 overflow-hidden bg-[#090a0e] text-[var(--text-primary)]" {...tourRoute("sessions", tourVariant)}>
      <div className="hidden h-full min-h-0 w-[22rem] shrink-0 lg:block xl:w-[23rem]" {...tourAnchor("sessions.conversation-rail")}>
        <SessionConversationRail
          search={search}
          onSearchChange={setSearch}
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          loading={sessionsResource.initialLoading}
          error={sessionsResource.error}
          unavailable={sessionsUnavailable}
          onRefresh={() => {
            void sessionsResource.refresh({ background: true, preserveError: true });
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
        <div {...tourAnchor("sessions.thread")}>
          <SessionThreadView
            botId={effectiveBotId}
            detail={activeDetail}
            summary={selectedSummary}
            pendingMessages={visiblePendingMessages}
            loading={Boolean(selectedSessionId && detailResource.initialLoading && !activeDetail)}
            error={detailResource.error}
            showRailToggle={!isDesktop}
            onOpenRail={() => setMobileRailOpen(true)}
            showContextToggle={Boolean(selectedSummary)}
            onOpenContext={() => setMobileContextOpen(true)}
            onRetryPendingMessage={handleRetryPendingMessage}
            footer={
              <div {...tourAnchor("sessions.composer")}>
                <SessionChatComposer
                  botId={activeBotId}
                  onBotChange={handleBotChange}
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
              "fixed inset-y-0 left-0 z-[49] w-[min(24rem,calc(100vw-1rem))] overflow-hidden border-r border-[rgba(255,255,255,0.06)] bg-[#0d0e12] shadow-[0_28px_90px_rgba(0,0,0,0.42)] transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] lg:hidden",
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
              sessions={sessions}
              selectedSessionId={selectedSessionId}
              loading={sessionsResource.initialLoading}
              error={sessionsResource.error}
              unavailable={sessionsUnavailable}
              onRefresh={() => {
                void sessionsResource.refresh({ background: true, preserveError: true });
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
              "fixed inset-y-0 right-0 z-[49] w-[min(23rem,calc(100vw-1rem))] overflow-hidden border-l border-[rgba(255,255,255,0.06)] bg-[#0d0e12] shadow-[0_28px_90px_rgba(0,0,0,0.42)] transition-[opacity,transform] duration-220 ease-[cubic-bezier(0.16,1,0.3,1)] xl:hidden",
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
        <div className="flex h-full min-h-0 overflow-hidden bg-[#090a0e]">
          <div className="hidden h-full w-[22rem] shrink-0 border-r border-[rgba(255,255,255,0.06)] bg-[#0d0e12] lg:block">
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
            <div className="border-b border-[rgba(255,255,255,0.06)] px-4 py-4 sm:px-6">
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
            <div className="border-t border-[rgba(255,255,255,0.06)] px-4 py-4 sm:px-6">
              <div className="mx-auto max-w-[52rem] rounded-[1.5rem] border border-[rgba(255,255,255,0.08)] p-4">
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
