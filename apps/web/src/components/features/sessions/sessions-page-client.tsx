"use client";


import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
  useMediaQuery,
} from "@/hooks/use-animated-presence";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAppTour } from "@/hooks/use-app-tour";
import {
  keepPreviousData,
  type InfiniteData,
  useInfiniteQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useContentStable } from "@/hooks/use-content-stable";
import { useMinDurationFlag } from "@/hooks/use-min-duration-flag";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useToast } from "@/hooks/use-toast";
import {
  readCurrentUrlSearchParam,
  replaceUrlSearchParamsSilently,
  useUrlSyncedSearch,
} from "@/hooks/use-url-synced-search";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";
import type { ChatCommand } from "@/lib/contracts/chat-commands";
import type { Mention } from "@/lib/contracts/sessions";
import { ChatHeader } from "@/components/sessions/chat/chat-header";
import { ChatThread, type PendingChatMessage } from "@/components/sessions/chat/chat-thread";
import {
  collectArtifactsFromDetail,
  SessionArtifactRail,
} from "@/components/sessions/context/session-artifact-rail";
import { SessionRail } from "@/components/sessions/rail/session-rail";
import { NewRoomDialog } from "@/components/sessions/rail/new-room-dialog";
import { RoomChatPane } from "@/components/sessions/chat/room-chat-pane";
import { useRooms, type RoomEntry } from "@/hooks/use-rooms";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { SessionsRouteLoading } from "@/components/layout/route-loading";
import { useSessionStream } from "@/hooks/use-session-stream";
import type { SessionStreamEvent } from "@/lib/contracts/sessions";
import type { SquadThreadOverviewResponse } from "@/lib/squads";
import { parseArtifactReadyPayload } from "@/lib/contracts/artifacts";
import { executionArtifactDedupeKey } from "@/components/sessions/artifacts/artifact-detail";
import {
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import {
  DASHBOARD_CACHE_GC_MS,
  DASHBOARD_CACHE_STALE_MS,
  DASHBOARD_PAGE_SIZE,
  mergePaginatedItems,
  normalizePaginatedListResponse,
  type PaginatedListResponse,
} from "@/lib/pagination";
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

const SESSION_FETCH_LIMIT = DASHBOARD_PAGE_SIZE;
const SESSION_THREAD_PAGE_SIZE = 24;
const CHAT_HISTORY_STALE_MS = 5 * 60 * 1000;
const CHAT_HISTORY_GC_MS = 15 * 60 * 1000;
const NEW_SESSION_PLACEHOLDER_ID = "__new_session__";
const EMPTY_SESSION_DETAIL_PAGES: SessionDetail[] = [];

type SessionPage = PaginatedListResponse<SessionSummary> & {
  unavailable?: boolean;
};

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

  const indexById = new Map<string, number>();
  const messages: SessionMessage[] = [];
  for (const page of orderedPages) {
    for (const message of page.messages) {
      const existingIndex = indexById.get(message.id);
      if (existingIndex !== undefined) {
        messages[existingIndex] = message;
        continue;
      }
      indexById.set(message.id, messages.length);
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
  const searchParams = useSearchParams();
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const [queryBotId, setQueryBotId] = useState<string | null>(() =>
    searchParams.get("agent"),
  );
  const searchState = useUrlSyncedSearch({
    debounceMs: 220,
    initialValue: searchParams.get("search"),
    syncToUrl: false,
  });

  const [activeBotId, setActiveBotId] = useState<string | undefined>(() =>
    normalizeSelectedBotId(queryBotId, availableBotIds)
  );
  const search = searchState.value;
  const setSearch = searchState.setValue;
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
  const [contextPanelOpen, setContextPanelOpen] = useState(true);
  const [pendingDeleteSession, setPendingDeleteSession] =
    useState<SessionSummary | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(
    searchParams.get("room"),
  );
  const [activeRoomDetail, setActiveRoomDetail] =
    useState<SquadThreadOverviewResponse | null>(null);
  const [newRoomOpen, setNewRoomOpen] = useState(false);
  const [threadScrolled, setThreadScrolled] = useState(false);
  const [pendingMessages, setPendingMessages] = useState<PendingChatMessage[]>([]);
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
  const { showToast } = useToast();
  const debouncedSearch = searchState.debouncedValue;

  useEffect(() => {
    const handlePopState = () => {
      setQueryBotId(readCurrentUrlSearchParam("agent") || null);
      setSelectedSessionId(readCurrentUrlSearchParam("session") || null);
      setSelectedRoomId(readCurrentUrlSearchParam("room") || null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

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
    replaceUrlSearchParamsSilently((params) => {
      if (activeBotId) params.set("agent", activeBotId);
      else params.delete("agent");

      if (debouncedSearch) params.set("search", debouncedSearch);
      else params.delete("search");

      if (selectedSessionId) params.set("session", selectedSessionId);
      else params.delete("session");

      if (selectedRoomId) params.set("room", selectedRoomId);
      else params.delete("room");
    });
  }, [
    activeBotId,
    availableBotIds.length,
    debouncedSearch,
    queryBotId,
    selectedRoomId,
    selectedSessionId,
  ]);

  const sessionsQueryKey = useMemo(
    () =>
      queryKeys.dashboard.sessionPages({
        search: debouncedSearch,
        limit: SESSION_FETCH_LIMIT,
      }),
    [debouncedSearch],
  );
  const fetchSessionsPage = useCallback(
    async ({
      signal,
      offset,
    }: {
      signal?: AbortSignal;
      offset: number;
    }): Promise<SessionPage> => {
      const response = await fetchControlPlaneDashboardJsonAllowError<
        PaginatedListResponse<SessionSummary>
      >(
        "/sessions",
        {
          signal,
          params: {
            paged: 1,
            limit: SESSION_FETCH_LIMIT,
            offset,
            search: debouncedSearch || null,
          },
          fallbackError: t("sessions.loadError"),
        },
      );
      const page = normalizePaginatedListResponse<SessionSummary>(
        response.data,
        SESSION_FETCH_LIMIT,
        offset,
      );
      return {
        ...page,
        unavailable: !response.ok,
      };
    },
    [debouncedSearch, t],
  );
  const refreshSessionsFirstPage = useCallback(async () => {
    try {
      const firstPage = await fetchSessionsPage({ offset: 0 });
      queryClient.setQueryData<InfiniteData<SessionPage, number>>(
        sessionsQueryKey,
        (current) => {
          if (!current) {
            return {
              pages: [firstPage],
              pageParams: [0],
            };
          }
          return {
            ...current,
            pages: [firstPage, ...current.pages.slice(1)],
            pageParams: current.pageParams.length > 0 ? current.pageParams : [0],
          };
        },
      );
    } catch {
      // Background freshness should not interrupt the active chat interaction.
    }
  }, [fetchSessionsPage, queryClient, sessionsQueryKey]);

  const sessionsQuery = useInfiniteQuery<SessionPage, Error>({
    queryKey: sessionsQueryKey,
    initialPageParam: 0,
    staleTime: DASHBOARD_CACHE_STALE_MS,
    gcTime: DASHBOARD_CACHE_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
    getNextPageParam: (lastPage) =>
      lastPage.page.has_more ? lastPage.page.next_offset : undefined,
    queryFn: async ({ signal, pageParam }) => {
      const offset = typeof pageParam === "number" ? pageParam : 0;
      return fetchSessionsPage({ signal, offset });
    },
  });

  const stableSessionsQuery = useStableQueryData({
    data: sessionsQuery.data,
    resetKey: JSON.stringify({ search: debouncedSearch, limit: SESSION_FETCH_LIMIT }),
    isPending: sessionsQuery.isPending,
    isFetching: sessionsQuery.isFetching,
    error: sessionsQuery.error,
  });
  const stableSessionsPayload = useContentStable(stableSessionsQuery.data ?? undefined);
  const sessions = useMemo(
    () =>
      mergePaginatedItems(
        stableSessionsPayload?.pages,
        (session) => `${session.bot_id}:${session.session_id}`,
      ),
    [stableSessionsPayload],
  );
  const sessionsUnavailable = stableSessionsPayload?.pages.some((page) => page.unavailable) ?? false;
  const loadMoreSessions = useCallback(() => {
    if (!sessionsQuery.hasNextPage || sessionsQuery.isFetchingNextPage) return;
    void sessionsQuery.fetchNextPage();
  }, [sessionsQuery]);
  const selectedSessionSummary = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessions]
  );
  const selectedSessionBotId = useMemo(
    () => normalizeSelectedBotId(selectedSessionSummary?.bot_id, availableBotIds),
    [availableBotIds, selectedSessionSummary?.bot_id],
  );
  const conversationPaneActive = !selectedRoomId;
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
            { queryKey: detailQueryKey },
            (current) => attachArtifactToSessionDetail(current, event.task_id, artifact),
          );
        }
      }
      if (streamInvalidateTimerRef.current) {
        clearTimeout(streamInvalidateTimerRef.current);
      }
      streamInvalidateTimerRef.current = setTimeout(() => {
        streamInvalidateTimerRef.current = null;
        void queryClient.invalidateQueries({ queryKey: detailQueryKey });
        void refreshSessionsFirstPage();
      }, 120);
    },
    [queryClient, detailQueryKey, refreshSessionsFirstPage],
  );

  const streamSessionId =
    selectedSessionId && selectedSessionId !== NEW_SESSION_PLACEHOLDER_ID
      ? selectedSessionId
      : null;
  const { connected: streamConnected } = useSessionStream({
    agentId: detailBotId ?? null,
    sessionId: streamSessionId,
    enabled: Boolean(conversationPaneActive && detailBotId && streamSessionId),
    onEvent: handleSessionStreamEvent,
  });

  const detailQuery = useControlPlaneQuery<SessionDetail>({
    tier: "realtime",
    queryKey: detailQueryKey,
    enabled: Boolean(conversationPaneActive && detailBotId && selectedSessionId),
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
  const latestHistoryBoundaryCursor = activeDetail?.page?.next_cursor ?? null;
  const olderDetailPagesQueryKey = useMemo(
    () =>
      queryKeys.dashboard.sessionOlderPages(
        detailBotId ?? "__disabled__",
        selectedSessionId ?? "__disabled__",
        latestHistoryBoundaryCursor ?? "__none__",
        SESSION_THREAD_PAGE_SIZE,
      ),
    [detailBotId, latestHistoryBoundaryCursor, selectedSessionId],
  );
  const olderDetailPagesEnabled = Boolean(
    conversationPaneActive &&
      detailBotId &&
      selectedSessionId &&
      latestHistoryBoundaryCursor,
  );
  const olderDetailPagesQuery = useInfiniteQuery({
    queryKey: olderDetailPagesQueryKey,
    enabled: olderDetailPagesEnabled,
    initialPageParam: latestHistoryBoundaryCursor ?? "",
    staleTime: CHAT_HISTORY_STALE_MS,
    gcTime: CHAT_HISTORY_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: ({ pageParam, signal }) => {
      const cursor = typeof pageParam === "string" ? pageParam : "";
      if (!detailBotId || !selectedSessionId || !cursor) {
        throw new Error(t("sessions.noSelection"));
      }
      return fetchControlPlaneDashboardJson<SessionDetail>(
        `/agents/${detailBotId}/sessions/${encodeURIComponent(selectedSessionId)}`,
        {
          signal,
          params: {
            limit: SESSION_THREAD_PAGE_SIZE,
            before: cursor,
          },
          fallbackError: t("sessions.loadError"),
        },
      );
    },
    getNextPageParam: (lastPage) => lastPage.page?.next_cursor ?? undefined,
  });
  const olderDetailPages = olderDetailPagesQuery.data?.pages ?? EMPTY_SESSION_DETAIL_PAGES;
  const loadedHistoryMessages = useMemo(
    () => mergeSessionHistoryPages(activeDetail, olderDetailPages),
    [activeDetail, olderDetailPages],
  );
  const selectedSummary = activeDetail?.summary ?? selectedSessionSummary;
  const effectiveBotId =
    normalizeSelectedBotId(selectedSummary?.bot_id, availableBotIds) ?? activeBotId;
  const oldestLoadedPage = olderDetailPages[olderDetailPages.length - 1] ?? activeDetail;
  const hasOlderMessages = Boolean(
    latestHistoryBoundaryCursor &&
      (olderDetailPages.length > 0
        ? oldestLoadedPage?.page?.has_more
        : activeDetail?.page?.has_more),
  );
  const loadingOlderDetailPages = olderDetailPagesQuery.isFetchingNextPage;
  const fetchOlderDetailPage = olderDetailPagesQuery.fetchNextPage;

  useEffect(() => {
    setActiveRoomDetail(null);
  }, [selectedRoomId]);

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
    void refreshSessionsFirstPage();
  }, [activeDetail, pendingRequest, refreshSessionsFirstPage]);

  useEffect(() => {
    if (stableSessionsQuery.initialLoading) return;
    if (isNewChatMode) return;
    if (selectedRoomId) return;
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
    selectedRoomId,
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
  }, []);

  const loadOlderMessages = useCallback(async () => {
    if (!hasOlderMessages || loadingOlderDetailPages) {
      return;
    }
    await fetchOlderDetailPage();
  }, [fetchOlderDetailPage, hasOlderMessages, loadingOlderDetailPages]);

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
      setSelectedRoomId(null);
      setContextPanelOpen(true);
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

  const handleSelectRoom = useCallback(
    (entry: RoomEntry) => {
      setSelectedRoomId(entry.thread.id);
      setSelectedSessionId(null);
      setContextPanelOpen(true);
      setNewChatSessionId(null);
      setIsNewChatMode(false);
      setComposerError(null);
      setPendingRequest(null);
      setPendingMessages([]);
      if (!isDesktop) {
        setMobileRailOpen(false);
      }
    },
    [isDesktop],
  );

  const handleRoomCreated = useCallback(
    (result: { threadId: string; squadId: string; workspaceId: string }) => {
      setNewRoomOpen(false);
      setSelectedRoomId(result.threadId);
      setSelectedSessionId(null);
      setContextPanelOpen(true);
      setNewChatSessionId(null);
      setIsNewChatMode(false);
      setComposerError(null);
      setPendingRequest(null);
      setPendingMessages([]);
      if (!isDesktop) {
        setMobileRailOpen(false);
      }
    },
    [isDesktop],
  );

  const handleRequestDeleteSession = useCallback((session: SessionSummary) => {
    setPendingDeleteSession(session);
  }, []);

  const handleConfirmDeleteSession = useCallback(async () => {
    const session = pendingDeleteSession;
    if (!session || deleteSubmitting) return;
    const targetBotId =
      normalizeSelectedBotId(session.bot_id, availableBotIds) ?? session.bot_id;
    setDeleteSubmitting(true);
    try {
      await mutateControlPlaneDashboardJson(
        `/agents/${targetBotId}/sessions/${encodeURIComponent(session.session_id)}`,
        {
          method: "DELETE",
          fallbackError: t("sessions.delete.failed", undefined),
        },
      );
      if (selectedSessionId === session.session_id) {
        setSelectedSessionId(null);
        resetThreadState();
      }
      setPendingDeleteSession(null);
      void refreshSessionsFirstPage();
    } catch (error) {
      const message =
        error instanceof Error && error.message.trim()
          ? error.message
          : t("sessions.delete.failed", undefined);
      showToast(message, "error");
    } finally {
      setDeleteSubmitting(false);
    }
  }, [
    availableBotIds,
    deleteSubmitting,
    pendingDeleteSession,
    refreshSessionsFirstPage,
    resetThreadState,
    selectedSessionId,
    showToast,
    t,
  ]);

  const handleNewChat = useCallback((agentId?: string) => {
    const nextSessionId = createClientSessionId();
    setActiveBotId((current) => {
      if (agentId) return normalizeSelectedBotId(agentId, availableBotIds);
      const candidate = selectedSummary?.bot_id ?? current;
      return normalizeSelectedBotId(candidate, availableBotIds) ?? current;
    });
    setSelectedSessionId(null);
    setSelectedRoomId(null);
    setContextPanelOpen(false);
    setNewChatSessionId(nextSessionId);
    setIsNewChatMode(true);
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
        void refreshSessionsFirstPage();
      } catch (error) {
        const message =
          error instanceof Error && error.message.trim()
            ? error.message
            : t("sessions.sendUnavailable");
        showToast(message, "error");
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
    [composerMentions, effectiveBotId, composerSubmitting, newChatSessionId, refreshSessionsFirstPage, selectedSessionId, showToast, t]
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
          // Context drawer was retired; the artifact rail surfaces the same
          // information inline.
          return;
        case "summarize": {
          const prompt =
            (action.payload?.prompt as string | undefined) ??
            t("chat.composer.summarizePrompt", undefined);
          void sendMessage(prompt);
          return;
        }
        case "switch-agent":
        case "rename-session":
        default:
          return;
      }
    },
    [handleNewChat, sendMessage, t],
  );

  const composerDisabled = !effectiveBotId;
  const showThinking = Boolean(
    pendingRequest ||
      (selectedSummary?.running_count && selectedSummary.running_count > 0) ||
      (selectedSummary?.latest_status === "running" ||
        selectedSummary?.latest_status === "retrying" ||
        selectedSummary?.latest_status === "stalled" ||
        selectedSummary?.latest_status === "degraded"),
  );

  const resolvedTitle = selectedSummary
    ? resolveSessionTitle(selectedSummary)
    : isNewChatMode
      ? t("chat.thread.empty", undefined)
      : t("chat.thread.empty", undefined);

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

  const roomsQuery = useRooms();
  const rooms = roomsQuery.rooms;
  const railSearchPending =
    searchState.isSearching ||
    (sessionsQuery.isFetching &&
      !sessionsQuery.isFetchingNextPage &&
      search.trim() === debouncedSearch);
  const railSessionsLoading = useMinDurationFlag(
    stableSessionsQuery.initialLoading || railSearchPending,
    180,
  );
  const railRoomsLoading = useMinDurationFlag(roomsQuery.loading, 180);
  const railRefreshing =
    stableSessionsQuery.refreshing || roomsQuery.refreshing || railSearchPending;
  const selectedRoomEntry = useMemo(
    () => rooms.find((entry) => entry.thread.id === selectedRoomId) ?? null,
    [rooms, selectedRoomId],
  );
  const sessionArtifacts = useMemo(
    () => collectArtifactsFromDetail(selectedRoomId ? null : activeDetail),
    [activeDetail, selectedRoomId],
  );
  const contextPanelAvailable = Boolean(
    selectedRoomEntry || (!selectedRoomId && sessionArtifacts.length > 0),
  );
  const chatDetailFetchingWithoutData = Boolean(
    selectedSessionId &&
      !selectedRoomId &&
      !stableDetailQuery.hasData &&
      detailQuery.isFetching,
  );
  const chatThreadLoading = useMinDurationFlag(
    Boolean(
      selectedSessionId &&
        !selectedRoomId &&
        (stableDetailQuery.initialLoading || chatDetailFetchingWithoutData),
    ),
    220,
  );

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
          rooms={rooms}
          selectedSessionId={selectedSessionId}
          selectedRoomId={selectedRoomId}
          onSelectSession={handleSelectSession}
          onSelectRoom={handleSelectRoom}
          onNewChat={handleNewChat}
          onNewRoom={() => setNewRoomOpen(true)}
          onDeleteSession={handleRequestDeleteSession}
          search={search}
          onSearchChange={setSearch}
          searching={railSearchPending}
          sessionsLoading={railSessionsLoading}
          roomsLoading={railRoomsLoading}
          refreshing={railRefreshing}
          hasMoreSessions={Boolean(sessionsQuery.hasNextPage)}
          loadingMoreSessions={sessionsQuery.isFetchingNextPage}
          onLoadMoreSessions={loadMoreSessions}
          error={stableSessionsQuery.showBlockingError ? sessionsQuery.error?.message ?? null : null}
          roomsError={roomsQuery.error?.message ?? null}
          unavailable={sessionsUnavailable}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col min-w-0" {...tourAnchor("sessions.thread")}>
        {selectedRoomId ? (
          <RoomChatPane
            threadId={selectedRoomId}
            onOpenRail={() => setMobileRailOpen(true)}
            showRailToggle
            onThreadDetailChange={setActiveRoomDetail}
          />
        ) : (
          <>
        <ChatHeader
          title={resolvedTitle}
          agentId={effectiveBotId ?? null}
          sessionId={streamSessionId}
          onOpenRail={() => setMobileRailOpen(true)}
          showRailToggle
          showContextToggle={contextPanelAvailable}
          contextPanelOpen={contextPanelOpen}
          onToggleContextPanel={() => setContextPanelOpen((current) => !current)}
          scrolled={threadScrolled}
          sessionActive={Boolean(
            selectedSummary &&
              (selectedSummary.latest_status === "running" ||
                selectedSummary.latest_status === "retrying" ||
                selectedSummary.latest_status === "stalled" ||
                selectedSummary.latest_status === "degraded" ||
                selectedSummary.latest_status === "queued"),
          )}
          sessionPaused={selectedSummary?.latest_status === "paused"}
        />
        <ChatThread
          messages={loadedHistoryMessages}
          pendingMessages={visiblePendingMessages}
          orphanExecutions={activeDetail?.orphan_executions ?? []}
          showThinking={showThinking}
          loading={chatThreadLoading}
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
                    ? t("sessions.composer.selectAgentToStart", undefined)
                    : null
                }
                error={composerError}
              />
            </div>
          }
        />
          </>
        )}
      </div>

      <SessionArtifactRail
        detail={selectedRoomId ? null : activeDetail}
        summary={selectedRoomId ? null : selectedSummary}
        room={selectedRoomEntry}
        open={selectedRoomId ? true : contextPanelOpen && contextPanelAvailable}
        onOpenChange={selectedRoomId ? undefined : setContextPanelOpen}
        onRoomArchived={() => {
          setSelectedRoomId(null);
          setContextPanelOpen(false);
        }}
        roomThreadMessages={selectedRoomId ? activeRoomDetail?.recentMessages ?? [] : []}
      />

      {mobileRailPresence.shouldRender ? (
        <>
          <button
            type="button"
            aria-label={t("chat.rail.close", undefined)}
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
            aria-label={t("chat.rail.title", undefined)}
          >
            <SessionRail
              sessions={sessions}
              rooms={rooms}
              selectedSessionId={selectedSessionId}
              selectedRoomId={selectedRoomId}
              onSelectSession={handleSelectSession}
              onSelectRoom={handleSelectRoom}
              onNewChat={handleNewChat}
              onNewRoom={() => setNewRoomOpen(true)}
              onDeleteSession={handleRequestDeleteSession}
              search={search}
              onSearchChange={setSearch}
              searching={railSearchPending}
              sessionsLoading={railSessionsLoading}
              roomsLoading={railRoomsLoading}
              refreshing={railRefreshing}
              hasMoreSessions={Boolean(sessionsQuery.hasNextPage)}
              loadingMoreSessions={sessionsQuery.isFetchingNextPage}
              onLoadMoreSessions={loadMoreSessions}
              error={stableSessionsQuery.showBlockingError ? sessionsQuery.error?.message ?? null : null}
              roomsError={roomsQuery.error?.message ?? null}
              unavailable={sessionsUnavailable}
              onClose={() => setMobileRailOpen(false)}
              className="border-r-0"
            />
          </div>
        </>
      ) : null}

      <NewRoomDialog
        open={newRoomOpen}
        onClose={() => setNewRoomOpen(false)}
        onCreated={handleRoomCreated}
      />

      <ConfirmationDialog
        open={Boolean(pendingDeleteSession)}
        title={t("sessions.delete.title", undefined)}
        message={t("sessions.delete.message", undefined)}
        confirmLabel={t("sessions.delete.confirm", undefined)}
        confirmBusy={deleteSubmitting}
        confirmBusyLabel={t("sessions.delete.deleting", undefined)}
        onConfirm={() => void handleConfirmDeleteSession()}
        onCancel={() => {
          if (deleteSubmitting) return;
          setPendingDeleteSession(null);
        }}
      />
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
