"use client";

import {
  Fragment,
  type CSSProperties,
  type FormEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { keepPreviousData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, LoaderCircle, PanelLeft, PanelRight, Reply, Settings2, Users, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useOptionalAuth } from "@/components/providers/auth-provider";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { AgentGlyph } from "@/components/ui/agent-glyph";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useSquadThreadEvents } from "@/hooks/use-squad-thread-events";
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
} from "@/components/ui/popover";
import { AvatarGroupWithTooltips } from "@/components/ui/avatar-group-with-tooltip";
import {
  applyReplacement,
  detectTrigger,
  type TriggerMatch,
} from "@/components/sessions/chat/composer/trigger-detection";
import {
  extractRoomAgentMentionIds,
  roomAgentMentionLiteral,
  roomAgentMentionToken,
  RoomMentionRichText,
  type RoomAgentMentionMeta,
} from "@/components/sessions/chat/room-agent-mention";
import { RoomSettingsDrawer } from "@/components/sessions/chat/room-settings-drawer";
import {
  fetchControlPlaneDashboardJson,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { SquadThreadOverviewResponse } from "@/lib/squads";
import { cn } from "@/lib/utils";

interface RoomChatPaneProps {
  threadId: string;
  /** Notified when the user archives the room from settings. */
  onArchived?: () => void;
  onOpenRail?: () => void;
  showRailToggle?: boolean;
  showContextToggle?: boolean;
  contextPanelOpen?: boolean;
  onToggleContextPanel?: () => void;
  settingsOpen?: boolean;
  onSettingsOpenChange?: (open: boolean) => void;
  onThreadDetailChange?: (detail: SquadThreadOverviewResponse | null) => void;
}

const OPERATOR_AGENT_ID = "operator";
const ROOM_THREAD_PAGE_SIZE = 32;
const ROOM_HISTORY_STALE_MS = 5 * 60 * 1000;
const ROOM_HISTORY_GC_MS = 15 * 60 * 1000;
const TOP_LOAD_THRESHOLD_PX = 320;
const EMPTY_ROOM_DETAIL_PAGES: SquadThreadOverviewResponse[] = [];
const AGENT_MESSAGE_ACCENTS = [
  "#22C7D8",
  "#7C8CFF",
  "#56C271",
  "#F2A93B",
  "#E879B4",
  "#A78BFA",
  "#5ED0A9",
  "#F9735B",
];

type RoomMessage = SquadThreadOverviewResponse["recentMessages"][number];
type ReplyDraft = {
  messageId: number;
  fromAgent: string | null;
  label: string;
  excerpt: string;
  targetAgentId: string | null;
};

function mergeRoomMessagePages(
  latestDetail: SquadThreadOverviewResponse | null,
  olderDetails: SquadThreadOverviewResponse[],
): RoomMessage[] {
  const orderedPages = [...olderDetails].reverse();
  if (latestDetail) {
    orderedPages.push(latestDetail);
  }

  const indexById = new Map<number, number>();
  const messages: RoomMessage[] = [];
  for (const page of orderedPages) {
    for (const message of page.recentMessages ?? []) {
      const existingIndex = indexById.get(message.id);
      if (existingIndex !== undefined) {
        messages[existingIndex] = message;
        continue;
      }
      indexById.set(message.id, messages.length);
      messages.push(message);
    }
  }
  return messages.sort((a, b) => a.id - b.id);
}

function isOperator(message: RoomMessage): boolean {
  return (message.from ?? "").toLowerCase() === OPERATOR_AGENT_ID;
}

function isUserAuthored(message: RoomMessage): boolean {
  // The squad backend assigns "user_input" type for operator-posted messages
  // and uses "agent_text" / "task_*" / "system_event" for non-user payloads.
  if (message.type === "user_input") return true;
  if (message.type === "system_event") return false;
  return isOperator(message);
}

function formatTime(value: string | null): string {
  if (!value) return "";
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(ts);
}

function formatDayLabel(value: string | null): string | null {
  if (!value) return null;
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(ts);
}

function sameMessageDay(a: string | null, b: string | null): boolean {
  if (!a || !b) return false;
  const first = new Date(a);
  const second = new Date(b);
  if (Number.isNaN(first.getTime()) || Number.isNaN(second.getTime())) return false;
  return first.toDateString() === second.toDateString();
}

function messageRef(messageId: number): string {
  return `msg-${messageId}`;
}

function replyExcerpt(content: string): string {
  const flat = content.replace(/\s+/g, " ").trim();
  if (flat.length <= 96) return flat;
  return `${flat.slice(0, 93)}...`;
}

function isReplyTargetAgent(message: RoomMessage): boolean {
  const from = (message.from ?? "").trim();
  if (!from) return false;
  if (isUserAuthored(message)) return false;
  if (from === "system" || from === "squad_router" || from.startsWith("operator:")) return false;
  return true;
}

function senderInitials(value: string): string {
  const parts = value
    .trim()
    .split(/[\s_.-]+/)
    .filter(Boolean);
  const initials = parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return initials || value.trim().slice(0, 2).toUpperCase() || "?";
}

function readableAvatarTextColor(background: string | null | undefined): string {
  if (!background?.startsWith("#")) return "var(--text-primary)";
  const hex = background.replace("#", "");
  if (hex.length !== 6) return "var(--text-primary)";
  const r = Number.parseInt(hex.slice(0, 2), 16);
  const g = Number.parseInt(hex.slice(2, 4), 16);
  const b = Number.parseInt(hex.slice(4, 6), 16);
  if ([r, g, b].some(Number.isNaN)) return "var(--text-primary)";
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return luminance > 0.66 ? "#111111" : "#ffffff";
}

function fallbackAgentAccent(seed: string): string {
  let hash = 2166136261 >>> 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return AGENT_MESSAGE_ACCENTS[hash % AGENT_MESSAGE_ACCENTS.length] ?? "#A7ADB4";
}

function MessageSenderAvatar({
  label,
  color,
  imageUrl,
}: {
  label: string;
  color: string | null;
  imageUrl?: string | null;
}) {
  const isAgent = Boolean(color);
  const accentColor = color ?? null;
  const avatarStyle = isAgent
    ? ({
        "--message-agent-color": accentColor,
        backgroundColor: `color-mix(in srgb, ${accentColor} 18%, var(--panel-strong))`,
        borderColor: `color-mix(in srgb, ${accentColor} 42%, var(--divider-hair))`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${accentColor} 18%, transparent)`,
      } as CSSProperties)
    : undefined;
  return (
    <Avatar
      className={cn(
        "relative h-9 w-9 overflow-hidden rounded-[0.65rem] border bg-[var(--panel-strong)] shadow-[var(--shadow-xs)]",
        isAgent ? "border-[color:var(--message-agent-color)]" : "border-[color:var(--divider-hair)]",
      )}
      style={avatarStyle}
    >
      {imageUrl ? (
        <AvatarImage
          src={imageUrl}
          alt={label}
          className="h-full w-full rounded-[0.65rem] object-cover"
          referrerPolicy="no-referrer"
        />
      ) : null}
      {isAgent ? (
        <>
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-95"
            style={{
              background: `radial-gradient(circle at 28% 22%, color-mix(in srgb, ${accentColor} 34%, transparent), transparent 46%)`,
            }}
          />
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-1 right-1 h-2 w-2 rounded-full ring-2 ring-[var(--canvas)]"
            style={{ backgroundColor: accentColor ?? undefined }}
          />
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-1 left-1 w-0.5 rounded-full"
            style={{ backgroundColor: accentColor ?? undefined }}
          />
        </>
      ) : null}
      <AvatarFallback
        className={cn(
          "relative z-[1] rounded-[0.65rem] border-0 bg-transparent font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.02em]",
          isAgent && "pl-0.5",
        )}
        style={{
          color: isAgent
            ? readableAvatarTextColor(accentColor)
            : "var(--text-primary)",
        }}
      >
        {senderInitials(label)}
      </AvatarFallback>
    </Avatar>
  );
}

export function RoomChatPane({
  threadId,
  onArchived,
  onOpenRail,
  showRailToggle = false,
  showContextToggle = false,
  contextPanelOpen = false,
  onToggleContextPanel,
  settingsOpen: controlledSettingsOpen,
  onSettingsOpenChange,
  onThreadDetailChange,
}: RoomChatPaneProps) {
  const { t } = useAppI18n();
  const auth = useOptionalAuth();
  const { agents } = useAgentCatalog();
  const queryClient = useQueryClient();
  const [internalSettingsOpen, setInternalSettingsOpen] = useState(false);
  const settingsOpen = controlledSettingsOpen ?? internalSettingsOpen;
  const setSettingsOpen = onSettingsOpenChange ?? setInternalSettingsOpen;
  const [draft, setDraft] = useState("");
  const [replyDraft, setReplyDraft] = useState<ReplyDraft | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const prependAnchorRef = useRef<{ scrollTop: number; scrollHeight: number } | null>(null);
  const loadOlderLockRef = useRef(false);
  const previousMessageCountRef = useRef(0);
  const [mentionTrigger, setMentionTrigger] = useState<TriggerMatch | null>(null);
  const [mentionActiveIndex, setMentionActiveIndex] = useState(0);

  const query = useControlPlaneQuery<SquadThreadOverviewResponse>({
    tier: "realtime",
    queryKey: queryKeys.dashboard.squadThread(threadId),
    refetchInterval: 15_000,
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadThreadOverviewResponse>(
        `/squads/threads/${threadId}`,
        {
          signal,
          params: {
            message_limit: ROOM_THREAD_PAGE_SIZE,
          },
          fallbackError: t("sessions.room.loadError", {
            defaultValue: "Could not load this room.",
          }),
        },
      ),
  });

  const stable = useStableQueryData<SquadThreadOverviewResponse>({
    data: query.data,
    resetKey: threadId,
    isCompatible: (data) => data.thread.id === threadId,
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.error,
  });

  const onLiveEvent = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.dashboard.squadThread(threadId),
      exact: true,
    });
  }, [queryClient, threadId]);
  useSquadThreadEvents({ threadId, onEvent: onLiveEvent });

  const detail = stable.data ?? null;
  const latestHistoryBoundaryCursor = detail?.page?.nextCursor ?? null;
  const olderDetailPagesQueryKey = useMemo(
    () =>
      queryKeys.dashboard.squadThreadOlderPages(
        threadId || "__disabled__",
        latestHistoryBoundaryCursor ?? "__none__",
        ROOM_THREAD_PAGE_SIZE,
      ),
    [latestHistoryBoundaryCursor, threadId],
  );
  const olderDetailPagesQuery = useInfiniteQuery({
    queryKey: olderDetailPagesQueryKey,
    enabled: Boolean(threadId && latestHistoryBoundaryCursor),
    initialPageParam: latestHistoryBoundaryCursor ?? "",
    staleTime: ROOM_HISTORY_STALE_MS,
    gcTime: ROOM_HISTORY_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: ({ pageParam, signal }) => {
      const cursor = typeof pageParam === "string" ? pageParam : "";
      if (!threadId || !cursor) {
        throw new Error(
          t("sessions.room.loadError", {
            defaultValue: "Could not load this room.",
          }),
        );
      }
      return fetchControlPlaneDashboardJson<SquadThreadOverviewResponse>(
        `/squads/threads/${threadId}`,
        {
          signal,
          params: {
            message_limit: ROOM_THREAD_PAGE_SIZE,
            before: cursor,
          },
          fallbackError: t("sessions.room.loadError", {
            defaultValue: "Could not load this room.",
          }),
        },
      );
    },
    getNextPageParam: (lastPage) => lastPage.page?.nextCursor ?? undefined,
  });
  const activeOlderDetailPages = olderDetailPagesQuery.data?.pages ?? EMPTY_ROOM_DETAIL_PAGES;
  const messages = useMemo<RoomMessage[]>(
    () => mergeRoomMessagePages(detail, activeOlderDetailPages),
    [activeOlderDetailPages, detail],
  );
  useEffect(() => {
    onThreadDetailChange?.(detail);
  }, [detail, onThreadDetailChange]);

  useEffect(() => {
    setReplyDraft(null);
    setSubmitError(null);
    setDraft("");
    prependAnchorRef.current = null;
    loadOlderLockRef.current = false;
    previousMessageCountRef.current = 0;
  }, [threadId]);

  const oldestLoadedPage = activeOlderDetailPages[activeOlderDetailPages.length - 1] ?? detail;
  const hasOlderMessages = Boolean(
    latestHistoryBoundaryCursor &&
      (activeOlderDetailPages.length > 0
        ? oldestLoadedPage?.page?.hasMore
        : detail?.page?.hasMore),
  );
  const loadingOlderDetailPages = olderDetailPagesQuery.isFetchingNextPage;
  const fetchOlderDetailPage = olderDetailPagesQuery.fetchNextPage;

  const loadOlderMessages = useCallback(async () => {
    if (!hasOlderMessages || loadingOlderDetailPages) {
      return;
    }
    await fetchOlderDetailPage();
  }, [fetchOlderDetailPage, hasOlderMessages, loadingOlderDetailPages]);

  const agentLabelMap = useMemo(() => {
    const map = new Map<string, { label: string; color: string }>();
    for (const agent of agents) {
      map.set(agent.id, { label: agent.label || agent.id, color: agent.color });
      map.set(agent.id.toLowerCase(), {
        label: agent.label || agent.id,
        color: agent.color,
      });
    }
    return map;
  }, [agents]);

  const labelForAgent = useCallback(
    (agentId: string | null): { label: string; color: string | null } => {
      if (!agentId) return { label: "system", color: null };
      const exact = agentLabelMap.get(agentId);
      if (exact) return { label: exact.label, color: exact.color };
      const lc = agentLabelMap.get(agentId.toLowerCase());
      if (lc) return { label: lc.label, color: lc.color };
      return { label: agentId, color: null };
    },
    [agentLabelMap],
  );

  const triggerLoadOlderMessages = useCallback(() => {
    const viewport = viewportRef.current;
    if (
      !viewport ||
      !hasOlderMessages ||
      loadingOlderDetailPages ||
      loadOlderLockRef.current
    ) {
      return;
    }
    loadOlderLockRef.current = true;
    prependAnchorRef.current = {
      scrollHeight: viewport.scrollHeight,
      scrollTop: viewport.scrollTop,
    };
    void Promise.resolve(loadOlderMessages()).finally(() => {
      loadOlderLockRef.current = false;
    });
  }, [hasOlderMessages, loadOlderMessages, loadingOlderDetailPages]);

  const handleScroll = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    if (
      viewport.scrollTop <= TOP_LOAD_THRESHOLD_PX &&
      hasOlderMessages &&
      !loadingOlderDetailPages &&
      !loadOlderLockRef.current
    ) {
      triggerLoadOlderMessages();
    }
  }, [hasOlderMessages, loadingOlderDetailPages, triggerLoadOlderMessages]);

  useEffect(() => {
    if (!loadingOlderDetailPages) loadOlderLockRef.current = false;
  }, [loadingOlderDetailPages]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || messages.length === 0) return;
    if (viewport.clientHeight <= 0) return;
    if (viewport.scrollHeight <= viewport.clientHeight + TOP_LOAD_THRESHOLD_PX) {
      triggerLoadOlderMessages();
    }
  }, [messages.length, triggerLoadOlderMessages]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const anchor = prependAnchorRef.current;
    if (anchor) {
      const delta = viewport.scrollHeight - anchor.scrollHeight;
      if (delta !== 0) {
        viewport.scrollTop = anchor.scrollTop + delta;
      }
      if (!loadingOlderDetailPages) prependAnchorRef.current = null;
      previousMessageCountRef.current = messages.length;
      return;
    }
    if (messages.length >= previousMessageCountRef.current) {
      const distanceFromBottom = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
      if (previousMessageCountRef.current === 0 || distanceFromBottom <= 180) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
    previousMessageCountRef.current = messages.length;
  }, [loadingOlderDetailPages, messages.length, threadId]);

  const participants = useMemo(
    () => detail?.participants ?? [],
    [detail?.participants],
  );
  const operatorAvatarLabel =
    auth?.operator?.display_name?.trim() ||
    auth?.operator?.username?.trim() ||
    auth?.operator?.email?.trim() ||
    t("sessions.room.you", { defaultValue: "You" });
  const operatorPhotoUrl = auth?.operator?.profile_photo_url ?? null;
  const participantAvatars = useMemo(
    () =>
      participants.map((participant) => {
        const meta = labelForAgent(participant.agentId);
        return {
          id: participant.agentId,
          name: meta.label,
          color: meta.color,
        };
      }),
    [labelForAgent, participants],
  );

  const startReply = useCallback(
    (message: RoomMessage) => {
      const meta = labelForAgent(message.from);
      setReplyDraft({
        messageId: message.id,
        fromAgent: message.from,
        label: isUserAuthored(message)
          ? t("sessions.room.you", { defaultValue: "You" })
          : meta.label,
        excerpt: replyExcerpt(message.content),
        targetAgentId: isReplyTargetAgent(message) ? message.from : null,
      });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    [labelForAgent, t],
  );

  const refreshMention = useCallback(() => {
    const node = textareaRef.current;
    if (!node) {
      setMentionTrigger(null);
      return;
    }
    const next = detectTrigger(node.value, node.selectionStart ?? 0, "@");
    setMentionTrigger(next);
  }, []);

  // Re-evaluate trigger every time the value changes (covers paste / typing
  // around the @-token without a fresh selection event).
  useEffect(() => {
    refreshMention();
  }, [draft, refreshMention]);

  // Reset the active highlight whenever the trigger window opens at a new
  // position — keeps keyboard navigation predictable.
  const triggerStart = mentionTrigger?.start ?? null;
  useEffect(() => {
    setMentionActiveIndex(0);
  }, [triggerStart]);

  const mentionLookup = useMemo(() => {
    const map = new Map<string, RoomAgentMentionMeta>();
    for (const participant of participants) {
      if (!participant.agentId) continue;
      const meta = labelForAgent(participant.agentId);
      const mention = {
        id: participant.agentId,
        label: meta.label,
        color: meta.color,
      };
      map.set(participant.agentId.toLowerCase(), mention);
      const displayToken = roomAgentMentionToken(mention).toLowerCase();
      if (!map.has(displayToken)) {
        map.set(displayToken, mention);
      }
    }
    return map;
  }, [labelForAgent, participants]);

  const mentionedAgentIdsInDraft = useMemo(
    () => new Set(extractRoomAgentMentionIds(draft, mentionLookup).map((agentId) => agentId.toLowerCase())),
    [draft, mentionLookup],
  );

  const mentionCandidates = useMemo(() => {
    if (!mentionTrigger) return [] as RoomAgentMentionMeta[];
    const q = mentionTrigger.query.trim().toLowerCase();
    const seen = new Set<string>();
    const items: RoomAgentMentionMeta[] = [];
    for (const participant of participants) {
      if (!participant.agentId || seen.has(participant.agentId.toLowerCase())) continue;
      seen.add(participant.agentId.toLowerCase());
      if (mentionedAgentIdsInDraft.has(participant.agentId.toLowerCase())) continue;
      const meta = labelForAgent(participant.agentId);
      if (
        !q ||
        participant.agentId.toLowerCase().includes(q) ||
        meta.label.toLowerCase().includes(q)
      ) {
        items.push({
          id: participant.agentId,
          label: meta.label,
          color: meta.color,
        });
      }
    }
    return items;
  }, [labelForAgent, mentionTrigger, mentionedAgentIdsInDraft, participants]);

  const applyMention = useCallback(
    (agentId: string) => {
      if (!mentionTrigger) return;
      const candidate = mentionCandidates.find((item) => item.id === agentId);
      const mention = candidate ?? mentionLookup.get(agentId.toLowerCase());
      if (!mention) return;
      const trailingSpace = draft.slice(mentionTrigger.end).startsWith(" ") ? "" : " ";
      const next = applyReplacement(
        draft,
        mentionTrigger,
        `${roomAgentMentionLiteral(mention)}${trailingSpace}`,
      );
      setDraft(next.text);
      setMentionTrigger(null);
      requestAnimationFrame(() => {
        const node = textareaRef.current;
        if (!node) return;
        node.focus();
        node.setSelectionRange(next.caret, next.caret);
      });
    },
    [draft, mentionCandidates, mentionLookup, mentionTrigger],
  );

  const handleSubmit = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      const content = draft.trim();
      if (!content || submitting) return;
      setSubmitting(true);
      setSubmitError(null);
      const mentionedAgentIds = extractRoomAgentMentionIds(content, mentionLookup);
      const targets = Array.from(
        new Set(
          [
            ...(replyDraft?.targetAgentId ? [replyDraft.targetAgentId] : []),
            ...mentionedAgentIds,
          ]
            .map((agentId) => agentId.trim())
            .filter(Boolean),
        ),
      );
      try {
        await mutateControlPlaneDashboardJson<{ messageId: number }>(
          `/squads/threads/${threadId}/messages`,
          {
            body: {
              content,
              from_agent: OPERATOR_AGENT_ID,
              replyToMessageId: replyDraft ? messageRef(replyDraft.messageId) : undefined,
              replyTargetAgentId: replyDraft?.targetAgentId ?? undefined,
              targetAgentIds: targets.length > 0 ? targets : undefined,
              metadata: replyDraft
                ? {
                    reply_excerpt: replyDraft.excerpt,
                    reply_to_agent_id: replyDraft.targetAgentId,
                    mentioned_agent_ids: mentionedAgentIds,
                  }
                : mentionedAgentIds.length > 0
                  ? { mentioned_agent_ids: mentionedAgentIds }
                  : undefined,
            },
            fallbackError: t("sessions.room.sendError", {
              defaultValue: "Could not post message.",
            }),
          },
        );
        setDraft("");
        setReplyDraft(null);
        void queryClient.invalidateQueries({
          queryKey: queryKeys.dashboard.squadThread(threadId),
          exact: true,
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setSubmitError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [draft, mentionLookup, queryClient, replyDraft, submitting, t, threadId],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (mentionTrigger && mentionCandidates.length > 0) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setMentionActiveIndex((idx) => (idx + 1) % mentionCandidates.length);
          return;
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          setMentionActiveIndex(
            (idx) =>
              (idx - 1 + mentionCandidates.length) % mentionCandidates.length,
          );
          return;
        }
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          const candidate = mentionCandidates[mentionActiveIndex];
          if (candidate) applyMention(candidate.id);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          setMentionTrigger(null);
          return;
        }
      }
      if (event.key !== "Enter") return;
      if (event.shiftKey) return;
      const submitModifier = event.metaKey || event.ctrlKey;
      if (!submitModifier) return;
      event.preventDefault();
      void handleSubmit();
    },
    [applyMention, handleSubmit, mentionActiveIndex, mentionCandidates, mentionTrigger],
  );

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[var(--canvas)]">
      <header
        className={cn(
          "flex h-14 shrink-0 items-center justify-between border-b border-[color:var(--divider-hair)] px-5 lg:px-6",
          "bg-[var(--canvas)]/95 backdrop-blur-[6px]",
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          {showRailToggle ? (
            <button
              type="button"
              onClick={onOpenRail}
              aria-label={t("chat.rail.openLabel", { defaultValue: "Open conversations" })}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] md:hidden"
            >
              <PanelLeft className="icon-sm" strokeWidth={1.75} aria-hidden />
            </button>
          ) : null}
          <Users
            className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]"
            strokeWidth={1.75}
            aria-hidden
          />
          <h2 className="m-0 truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
            {detail?.thread.title ||
              t("sessions.room.untitled", { defaultValue: "Untitled room" })}
          </h2>
        </div>
        <div className="flex items-center gap-2 overflow-hidden">
          <AvatarGroupWithTooltips
            avatars={participantAvatars}
            maxVisible={4}
            size="xs"
            showInitials={false}
            ariaLabel={t("sessions.room.participants", {
              defaultValue: "Room participants",
            })}
            className="hidden sm:inline-flex"
          />
          {showContextToggle ? (
            <button
              type="button"
              onClick={onToggleContextPanel}
              aria-label={
                contextPanelOpen
                  ? t("sessions.context.collapse", { defaultValue: "Collapse panel" })
                  : t("sessions.context.expand", { defaultValue: "Expand panel" })
              }
              aria-pressed={contextPanelOpen}
              className={cn(
                "hidden h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] lg:inline-flex",
                "text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
                contextPanelOpen && "bg-[var(--panel-soft)] text-[var(--text-primary)]",
              )}
            >
              <PanelRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label={t("sessions.room.settings.open", {
              defaultValue: "Room settings",
            })}
            className="ml-1 inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
          >
            <Settings2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      </header>

      <div
        ref={viewportRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        {!detail && (query.isPending || query.isFetching) ? (
          <div className="flex h-full items-center justify-center">
            <LoaderCircle
              className="h-4 w-4 animate-spin text-[var(--text-tertiary)]"
              strokeWidth={2}
              aria-hidden
            />
          </div>
        ) : stable.showBlockingError ? (
          <div className="mx-auto flex h-full w-full max-w-[480px] flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="m-0 text-[var(--font-size-sm)] text-[var(--tone-danger-dot)]">
              {query.error?.message ??
                t("sessions.room.loadError", {
                  defaultValue: "Could not load this room.",
                })}
            </p>
          </div>
        ) : messages.length === 0 ? (
          <div className="mx-auto flex h-full w-full max-w-[640px] flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="m-0 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {t("sessions.room.empty.eyebrow", { defaultValue: "New room" })}
            </p>
            <h1 className="m-0 text-[1.5rem] font-medium leading-[1.15] text-[var(--text-primary)] sm:text-[1.75rem]">
              {t("sessions.room.empty.title", {
                defaultValue: "Kick off the conversation",
              })}
            </h1>
            <p className="m-0 max-w-[420px] text-[var(--font-size-sm)] leading-[1.55] text-[var(--text-tertiary)]">
              {t("sessions.room.empty.helper", {
                defaultValue:
                  "Post a message; the coordinator will dispatch it to the right agents.",
              })}
            </p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[960px] flex-col px-6 pt-6 pb-8 lg:px-10">
            {loadingOlderDetailPages ? (
              <div className="flex justify-center py-3">
                <LoaderCircle
                  className="h-4 w-4 animate-spin text-[var(--text-tertiary)]"
                  strokeWidth={2}
                  aria-hidden
                />
              </div>
            ) : null}
            {messages.map((message, index) => {
              const previousMessage = index > 0 ? messages[index - 1] : null;
              const userAuthored = isUserAuthored(message);
              const meta = labelForAgent(message.from);
              const time = formatTime(message.createdAt);
              const dayLabel = formatDayLabel(message.createdAt);
              const previousDayLabel = previousMessage ? formatDayLabel(previousMessage.createdAt) : null;
              const showDaySeparator = Boolean(dayLabel && dayLabel !== previousDayLabel);
              const replySummary = message.replySummary ?? {};
              const openReplies = Number(replySummary.open ?? 0);
              const answeredReplies = Number(replySummary.answered ?? 0);
              const inReplyTo = message.inReplyTo ?? (message.metadata?.in_reply_to as string | undefined);
              const previousInReplyTo =
                previousMessage?.inReplyTo ??
                (previousMessage?.metadata?.in_reply_to as string | undefined);
              const isContinuation = Boolean(
                previousMessage &&
                  !showDaySeparator &&
                  !inReplyTo &&
                  !previousInReplyTo &&
                  previousMessage.from === message.from &&
                  previousMessage.type !== "coordinator_synthesis" &&
                  message.type !== "coordinator_synthesis" &&
                  sameMessageDay(previousMessage.createdAt, message.createdAt),
              );
              const authorLabel = userAuthored
                ? t("sessions.room.you", { defaultValue: "You" })
                : meta.label;
              const agentAccentColor =
                !userAuthored && message.type !== "system_event"
                  ? (meta.color ?? fallbackAgentAccent(message.from ?? authorLabel))
                  : null;
              return (
                <Fragment key={message.id}>
                  {showDaySeparator ? (
                    <div className="my-4 flex items-center gap-3 px-1">
                      <div className="h-px flex-1 bg-[var(--divider-hair)]" />
                      <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                        {dayLabel}
                      </span>
                      <div className="h-px flex-1 bg-[var(--divider-hair)]" />
                    </div>
                  ) : null}
                  <article
                    className={cn(
                      "group relative -mx-3 grid grid-cols-[3rem_minmax(0,1fr)_2rem] gap-x-3 rounded-[var(--radius-panel-sm)] px-3",
                      "transition-colors duration-[120ms] hover:bg-[var(--hover-tint)]",
                      isContinuation ? "py-0.5" : "py-2",
                      message.type === "system_event" && "opacity-90",
                    )}
                    aria-label={t("sessions.room.messageFrom", {
                      defaultValue: "Message from {{label}}",
                      label: authorLabel,
                    })}
                  >
                    <div className="flex justify-center pt-0.5">
                      {isContinuation ? (
                        <span className="w-full whitespace-nowrap pt-0.5 text-right font-mono text-[0.5625rem] leading-5 text-[var(--text-quaternary)] opacity-0 transition-opacity group-hover:opacity-100">
                          {time}
                        </span>
                      ) : (
                        <MessageSenderAvatar
                          label={userAuthored ? operatorAvatarLabel : authorLabel}
                          color={agentAccentColor}
                          imageUrl={userAuthored ? operatorPhotoUrl : null}
                        />
                      )}
                    </div>
                    <div className="min-w-0">
                      {!isContinuation ? (
                        <div className="flex min-w-0 items-baseline gap-2">
                          {agentAccentColor ? (
                            <span
                              className="h-1.5 w-1.5 shrink-0 rounded-full"
                              style={{ backgroundColor: agentAccentColor }}
                              aria-hidden
                            />
                          ) : null}
                          <span className="truncate text-[0.9375rem] font-semibold text-[var(--text-primary)]">
                            {authorLabel}
                          </span>
                          {time ? (
                            <span className="shrink-0 text-[0.75rem] text-[var(--text-quaternary)]">
                              {time}
                            </span>
                          ) : null}
                          {message.type === "coordinator_synthesis" ? (
                            <span className="shrink-0 rounded-full bg-[var(--tone-info-bg)] px-2 py-0.5 font-mono text-[0.5625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--tone-info-dot)]">
                              {t("sessions.room.reply.synthesized", {
                                defaultValue: "Synthesized",
                              })}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      {inReplyTo ? (
                        <div className="mt-1.5 flex max-w-full items-center gap-2 rounded-[var(--radius-panel-sm)] border border-[color:var(--divider-hair)] bg-[var(--panel-soft)] px-2 py-1 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
                          <Reply className="h-3 w-3 text-[var(--text-quaternary)]" strokeWidth={1.75} aria-hidden />
                          <span className="truncate">
                            {t("sessions.room.reply.parentPreview", {
                              defaultValue: "Linked reply in this thread",
                            })}
                          </span>
                          <span className="hidden font-mono text-[0.625rem] text-[var(--text-quaternary)] sm:inline">
                            {inReplyTo}
                          </span>
                        </div>
                      ) : null}
                      <div
                        className={cn(
                          "whitespace-pre-wrap break-words text-[0.9375rem] leading-[1.45] text-[var(--text-primary)]",
                          isContinuation ? "pt-0" : "pt-1",
                          message.type === "system_event" && "text-[var(--text-tertiary)]",
                        )}
                      >
                        <RoomMentionRichText text={message.content} mentionsByToken={mentionLookup} />
                      </div>
                      {openReplies > 0 || answeredReplies > 0 ? (
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
                          {openReplies > 0 ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--tone-warning-bg)] px-2 py-0.5 font-medium text-[var(--tone-warning-dot)]">
                              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
                              {t("sessions.room.reply.waiting", {
                                defaultValue: "{{count}} waiting",
                                count: openReplies,
                              })}
                            </span>
                          ) : null}
                          {answeredReplies > 0 ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--tone-success-bg)] px-2 py-0.5 font-medium text-[var(--tone-success-dot)]">
                              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
                              {t("sessions.room.reply.answered", {
                                defaultValue: "{{count}} answered",
                                count: answeredReplies,
                              })}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={() => startReply(message)}
                      className={cn(
                        "mt-0.5 inline-flex h-7 w-7 items-center justify-center justify-self-end rounded-[var(--radius-panel-sm)]",
                        "border border-[color:var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)] opacity-0 shadow-[var(--shadow-xs)]",
                        "transition-[opacity,background-color,color,border-color] duration-[120ms]",
                        "hover:border-[color:var(--border-strong)] hover:bg-[var(--panel-strong)] hover:text-[var(--text-primary)]",
                        "focus:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                        "group-hover:opacity-100",
                      )}
                      aria-label={t("sessions.room.reply.action", {
                        defaultValue: "Reply",
                      })}
                    >
                      <Reply className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                    </button>
                  </article>
                </Fragment>
              );
            })}
          </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="mx-auto w-full max-w-[760px] px-6 pb-5 pt-2 lg:px-8"
        aria-label={t("sessions.room.composer.placeholder", {
          defaultValue: "Send a message to this room…",
        })}
      >
        <Popover
          open={Boolean(mentionTrigger) && mentionCandidates.length > 0}
          onOpenChange={(next) => {
            if (!next) setMentionTrigger(null);
          }}
        >
        <PopoverAnchor asChild>
        <div
          className={cn(
            "flex flex-col rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] shadow-[var(--shadow-xs)]",
            "transition-[border-color,background-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "focus-within:border-[color:var(--border-strong)] focus-within:bg-[var(--panel)] focus-within:shadow-[0_0_0_1px_var(--border-strong)]",
            submitting && "opacity-70",
          )}
        >
          {replyDraft ? (
            <div className="mx-3 mt-3 flex items-start justify-between gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-strong)] px-3 py-2">
              <div className="min-w-0">
                <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                  {replyDraft.targetAgentId
                    ? t("sessions.room.reply.requesting", {
                        defaultValue: "Replying to {{label}}",
                        label: replyDraft.label,
                      })
                    : t("sessions.room.reply.linked", {
                        defaultValue: "Replying in thread",
                      })}
                </p>
                <p className="m-0 mt-0.5 truncate text-[0.75rem] text-[var(--text-secondary)]">
                  {replyDraft.excerpt ||
                    t("sessions.room.reply.noPreview", {
                      defaultValue: "No preview",
                    })}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReplyDraft(null)}
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                aria-label={t("sessions.room.reply.cancel", {
                  defaultValue: "Cancel reply",
                })}
              >
                <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </button>
            </div>
          ) : null}
          <div className="flex items-start gap-2 px-3 pt-3">
            <div className="relative min-h-[56px] max-h-[200px] flex-1">
              {draft ? (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words py-1 text-[var(--font-size-md)] leading-[1.5] text-[var(--text-primary)]"
                >
                  <RoomMentionRichText
                    text={draft}
                    mentionsByToken={mentionLookup}
                    variant="inline"
                  />
                </div>
              ) : null}
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  if (submitError) setSubmitError(null);
                }}
                onSelect={refreshMention}
                onClick={refreshMention}
                onKeyDown={handleKeyDown}
                disabled={submitting}
                rows={1}
                placeholder={t("sessions.room.composer.placeholder", {
                  defaultValue: "Send a message to this room…",
                })}
                className={cn(
                  "relative min-h-[56px] max-h-[200px] w-full resize-none bg-transparent py-1 text-[var(--font-size-md)] leading-[1.5]",
                  "caret-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] outline-none selection:bg-[var(--tone-info-bg)]",
                  draft ? "text-transparent" : "text-[var(--text-primary)]",
                )}
              />
            </div>
            <button
              type="submit"
              disabled={!draft.trim() || submitting}
              aria-label={t("chat.composer.send", { defaultValue: "Send" })}
              className={cn(
                "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                "transition-[background-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                draft.trim() && !submitting
                  ? "bg-[var(--accent)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)] active:scale-[0.96]"
                  : "bg-[var(--panel-strong)] text-[var(--text-quaternary)]",
              )}
            >
              {submitting ? (
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
              ) : (
                <ArrowUp className="h-3.5 w-3.5" strokeWidth={2} />
              )}
            </button>
          </div>
          <div className="px-4 pb-3 pt-1 text-[0.6875rem] text-[var(--text-quaternary)]">
            {t("sessions.room.composer.helper", {
              defaultValue:
                "Cmd/Ctrl + Enter to send. Type @ to mention a participant.",
            })}
          </div>
        </div>
        </PopoverAnchor>
        <PopoverContent
          align="start"
          side="top"
          sideOffset={8}
          className="composer-suggestions-panel w-[260px] max-w-[calc(100vw-3rem)] p-1"
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onPointerDownOutside={(event) => {
            const target = event.target as HTMLElement | null;
            if (target?.closest("textarea")) {
              event.preventDefault();
            }
          }}
        >
          <ul
            role="listbox"
            aria-label={t("sessions.room.mentions.label", {
              defaultValue: "Mention an agent",
            })}
            className="flex max-h-[260px] flex-col gap-0.5 overflow-y-auto"
          >
            {mentionCandidates.map((candidate, index) => {
              const isActive = index === mentionActiveIndex;
              return (
                <li
                  key={candidate.id}
                  role="option"
                  aria-selected={isActive}
                  onMouseEnter={() => setMentionActiveIndex(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyMention(candidate.id)}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-[0.8125rem]",
                    "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                    isActive
                      ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                  )}
                >
                  <AgentGlyph
                    agentId={candidate.id}
                    color={candidate.color ?? "#A7ADB4"}
                    shape="orb"
                    variant="list"
                    className="h-5 w-5 shrink-0"
                  />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-medium">
                      {candidate.label}
                    </span>
                    {candidate.label !== candidate.id ? (
                      <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                        {candidate.id}
                      </span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </PopoverContent>
        </Popover>
        {submitError ? (
          <p className="mt-2 px-1 text-[0.75rem] text-[var(--tone-danger-dot)]">
            {submitError}
          </p>
        ) : null}
      </form>

      <RoomSettingsDrawer
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        threadId={threadId}
        onArchived={onArchived}
      />
    </div>
  );
}
