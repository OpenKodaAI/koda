"use client";


import { Suspense, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
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
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";
import type { ChatCommand } from "@/lib/contracts/chat-commands";
import type { Mention } from "@/lib/contracts/sessions";
import { ChatHeader } from "@/components/sessions/chat/chat-header";
import { ChatThread, type PendingChatMessage } from "@/components/sessions/chat/chat-thread";
import { SessionContextDrawer } from "@/components/sessions/context/session-context-drawer";
import { SessionRail } from "@/components/sessions/rail/session-rail";
import { SessionsRouteLoading } from "@/components/layout/route-loading";
import { useSessionStream } from "@/hooks/use-session-stream";
import type { SessionStreamEvent } from "@/lib/contracts/sessions";
import { parseArtifactReadyPayload } from "@/lib/contracts/artifacts";
import { executionArtifactDedupeKey } from "@/components/sessions/artifacts/artifact-detail";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import type {
  ExecutionArtifact,
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

function createClientSessionId() {
  const id =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `session-${id}`;
}

function artifactReadyEventToExecutionArtifact(
  event: SessionStreamEvent,
): ExecutionArtifact | null {
  const payload = parseArtifactReadyPayload(event.payload);
  if (!payload) return null;
  const artifact = payload.artifact;
  const executionId = artifact.source_execution_id ?? (event.task_id ? String(event.task_id) : null);
  const path = artifact.path ?? null;
  const url = artifact.url ?? null;
  return {
    id: artifact.id,
    label: artifact.label ?? artifact.id,
    kind: artifact.kind,
    content: { path, url },
    description: artifact.label ?? artifact.kind,
    summary: artifact.label ?? artifact.kind,
    url,
    path,
    mime_type: artifact.mime_type ?? null,
    size_bytes: artifact.size_bytes ?? null,
    source_type: "runtime_artifact",
    status: "complete",
    text_content: null,
    metadata: {
      runtime_artifact_id: artifact.id,
      source_execution_id: executionId,
    },
    visual_paths: artifact.kind === "image" && path ? [path] : [],
    preview_image_url: artifact.kind === "image" && url?.startsWith("http") ? url : null,
    preview_image_path: artifact.kind === "image" ? path : null,
    domain: artifact.domain ?? null,
    site_name: null,
    unavailable: false,
  };
}

function attachArtifactToSessionDetail(
  detail: SessionDetail | undefined,
  taskId: number | null,
  artifact: ExecutionArtifact,
): SessionDetail | undefined {
  if (!detail || taskId === null) return detail;
  let changed = false;
  const artifactKey = executionArtifactDedupeKey(artifact);
  if (
    detail.messages.some((message) =>
      message.artifacts?.some((item) => executionArtifactDedupeKey(item) === artifactKey),
    )
  ) {
    return detail;
  }
  const messages = detail.messages.map((message) => {
    if (message.role !== "assistant" || message.linked_execution?.task_id !== taskId) {
      return message;
    }
    const existing = message.artifacts ?? [];
    if (existing.some((item) => executionArtifactDedupeKey(item) === artifactKey)) {
      return message;
    }
    changed = true;
    return { ...message, artifacts: [...existing, artifact] };
  });
  if (changed) return { ...detail, messages };

  const linkedExecution =
    detail.messages.find((message) => message.linked_execution?.task_id === taskId)
      ?.linked_execution ??
    detail.orphan_executions.find((execution) => execution.task_id === taskId) ??
    null;
  const timestamp =
    linkedExecution?.completed_at ??
    linkedExecution?.started_at ??
    linkedExecution?.created_at ??
    new Date().toISOString();
  const syntheticAssistant: SessionMessage = {
    id: `artifact-${taskId}-${artifactKey}`,
    role: "assistant",
    text: "",
    timestamp,
    model: linkedExecution?.model ?? null,
    cost_usd: linkedExecution?.cost_usd ?? null,
    query_id: taskId > 0 ? -taskId : -1,
    session_id: detail.summary.session_id,
    error: linkedExecution?.status === "failed",
    linked_execution: linkedExecution,
    artifacts: [artifact],
  };
  return {
    ...detail,
    messages: [...messages, syntheticAssistant],
    orphan_executions: detail.orphan_executions.filter((execution) => execution.task_id !== taskId),
  };
}

function normalizeSelectedBotId(
  candidate: string | null | undefined,
  availableBotIds: string[],
) {
  if (!candidate) return undefined;
  if (availableBotIds.length === 0) return candidate;
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
  const [newChatSessionId, setNewChatSessionId] = useState<string | null>(null);
  const [isNewChatMode, setIsNewChatMode] = useState(false);
  const [draft, setDraft] = useState("");
  const [composerMentions, setComposerMentions] = useState<Mention[]>([]);
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
  const streamInvalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoSelectedContextRef = useRef<string | null>(null);

  const queryClient = useQueryClient();
  const deferredSearch = useDeferredValue(search.trim());
  const debouncedSearch = useDebouncedValue(deferredSearch, 220);

  useEffect(() => {
    if (availableBotIds.length === 0) {
      setActiveBotId((current) => current ?? queryBotId ?? undefined);
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

  useEffect(
    () => () => {
      if (streamInvalidateTimerRef.current) {
        clearTimeout(streamInvalidateTimerRef.current);
      }
    },
    [],
  );

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
    if (queryBotId && availableBotIds.length === 0) return;
    const params = new URLSearchParams(searchParams.toString());
    if (activeBotId) {
      params.set("agent", activeBotId);
    } else {
      params.delete("agent");
    }
    if (debouncedSearch) {
      params.set("search", debouncedSearch);
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
  }, [
    activeBotId,
    availableBotIds.length,
    debouncedSearch,
    pathname,
    queryBotId,
    router,
    searchParams,
    selectedSessionId,
  ]);

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

  const stableSessionsQuery = useStableQueryData({
    data: sessionsQuery.data,
    resetKey: "dashboard:sessions",
    isPending: sessionsQuery.isPending,
    isFetching: sessionsQuery.isFetching,
    error: sessionsQuery.error,
  });
  const stableSessionsPayload = useContentStable(stableSessionsQuery.data ?? undefined);
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
      if (event.type === "artifact_ready") {
        const artifact = artifactReadyEventToExecutionArtifact(event);
        if (artifact) {
          queryClient.setQueriesData<SessionDetail>(
            { queryKey: detailQueryBaseKey },
            (current) => attachArtifactToSessionDetail(current, event.task_id, artifact),
          );
        }
      }
      if (streamInvalidateTimerRef.current) {
        clearTimeout(streamInvalidateTimerRef.current);
      }
      streamInvalidateTimerRef.current = setTimeout(() => {
        streamInvalidateTimerRef.current = null;
        void queryClient.invalidateQueries({ queryKey: detailQueryBaseKey });
        void queryClient.invalidateQueries({ queryKey: sessionsQueryKey });
      }, 120);
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

  const stableDetailQuery = useStableQueryData({
    data: detailQuery.data,
    resetKey: [detailBotId ?? "", selectedSessionId ?? ""],
    isCompatible: (detail) => detail.summary.session_id === selectedSessionId,
    isPending: detailQuery.isPending,
    isFetching: detailQuery.isFetching,
    error: detailQuery.error,
  });
  const stableDetailPayload = useContentStable(stableDetailQuery.data ?? undefined);
  const activeDetail = stableDetailPayload ?? null;
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
    if (stableSessionsQuery.initialLoading) return;
    if (isNewChatMode) return;
    const contextKey = `${activeBotId ?? "*"}:${debouncedSearch || "*"}`;
    if (autoSelectedContextRef.current === contextKey) return;
    if (!selectedSessionId && sessions.length > 0 && isDesktop) {
      autoSelectedContextRef.current = contextKey;
      setSelectedSessionId(sessions[0].session_id);
    }
  }, [
    activeBotId,
    debouncedSearch,
    isDesktop,
    isNewChatMode,
    selectedSessionId,
    sessions,
    stableSessionsQuery.initialLoading,
  ]);

  const visiblePendingMessages = useMemo(() => {
    const targetSessionId = selectedSessionId ?? newChatSessionId ?? NEW_SESSION_PLACEHOLDER_ID;
    return pendingMessages.filter((message) => message.session_id === targetSessionId);
  }, [newChatSessionId, pendingMessages, selectedSessionId]);

  const resetThreadState = useCallback(() => {
    setDraft("");
    setComposerError(null);
    setPendingRequest(null);
    setPendingMessages([]);
    setOlderDetailPages([]);
    setLoadingOlderDetailPages(false);
  }, []);

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
      setNewChatSessionId(null);
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
      setNewChatSessionId(null);
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

  const handleNewChat = useCallback((agentId?: string) => {
    const nextSessionId = createClientSessionId();
    setActiveBotId((current) => {
      if (agentId) return normalizeSelectedBotId(agentId, availableBotIds);
      const candidate = selectedSummary?.bot_id ?? current;
      return normalizeSelectedBotId(candidate, availableBotIds) ?? current;
    });
    setSelectedSessionId(null);
    setNewChatSessionId(nextSessionId);
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
      const draftSessionId = options?.sessionId ?? selectedSessionId ?? newChatSessionId ?? createClientSessionId();
      if (!selectedSessionId && !newChatSessionId) {
        setNewChatSessionId(draftSessionId);
      }
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
        const mentionsPayload = composerMentions.length > 0 ? composerMentions : undefined;
        const response = await mutateControlPlaneDashboardJson<SessionSendResponse>(
          `/agents/${sendBotId}/sessions/messages`,
          {
            fallbackError: t("sessions.sendUnavailable"),
            body: {
              text: trimmedText,
              session_id: draftSessionId,
              ...(mentionsPayload ? { mentions: mentionsPayload } : {}),
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
        setNewChatSessionId(null);
        setSelectedSessionId(resolvedSessionId);
        setIsNewChatMode(false);
        setDraft("");
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
    [composerMentions, effectiveBotId, composerSubmitting, newChatSessionId, queryClient, selectedSessionId, sessionsQueryKey, t]
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

  const handleCommand = useCallback(
    (command: ChatCommand) => {
      const action = command.action;
      if (action.kind !== "execute") return;
      switch (action.type) {
        case "new-session":
        case "clear-thread":
          handleNewChat();
          return;
        case "open-context":
          if (selectedSummary) setContextDrawerOpen(true);
          return;
        case "summarize": {
          const prompt =
            (action.payload?.prompt as string | undefined) ??
            t("chat.composer.summarizePrompt", {
              defaultValue: "Summarize this conversation so far.",
            });
          void sendMessage(prompt);
          return;
        }
        case "switch-agent":
        case "rename-session":
        default:
          return;
      }
    },
    [handleNewChat, selectedSummary, sendMessage, t],
  );

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
    stableSessionsQuery.showBlockingError || (sessionsUnavailable && sessions.length === 0)
      ? "unavailable"
      : stableSessionsQuery.initialLoading && sessions.length === 0
        ? "loading"
        : sessions.length === 0
          ? "empty"
          : "default";

  return (
    <div
      className="flex h-full min-h-0 overflow-hidden bg-[var(--canvas)] text-[var(--text-primary)]"
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
          loading={stableSessionsQuery.initialLoading}
          error={stableSessionsQuery.showBlockingError ? sessionsQuery.error?.message ?? null : null}
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
          loading={Boolean(selectedSessionId && stableDetailQuery.initialLoading)}
          error={stableDetailQuery.showBlockingError ? detailQuery.error?.message ?? null : null}
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
                onCommandExecute={handleCommand}
                onMentionsChange={setComposerMentions}
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
              "app-overlay-backdrop !z-[48] cursor-default border-0 md:hidden",
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
              loading={stableSessionsQuery.initialLoading}
              error={stableSessionsQuery.showBlockingError ? sessionsQuery.error?.message ?? null : null}
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
    <Suspense fallback={<SessionsRouteLoading />}>
      <SessionsPageContent />
    </Suspense>
  );
}
