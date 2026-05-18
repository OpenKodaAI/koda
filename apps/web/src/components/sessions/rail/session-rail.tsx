"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { LoaderCircle, MessageSquare, Plus, Search, Users, X } from "lucide-react";
import { SessionRow } from "@/components/sessions/rail/session-row";
import { RoomRow } from "@/components/sessions/rail/room-row";
import { RailSearch } from "@/components/sessions/rail/rail-search";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { SessionSummary } from "@/lib/types";
import type { RoomEntry } from "@/hooks/use-rooms";
import { fetchAgentCatalogPage } from "@/lib/agent-catalog-pages";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger, PopoverClose } from "@/components/ui/popover";
import { AgentGlyph } from "@/components/ui/agent-glyph";

type CreateMode = "conversation" | "room";

const NEW_CHAT_AGENT_PAGE_SIZE = 8;
const NEW_CHAT_AGENT_SCROLL_THRESHOLD = 32;

interface SessionRailProps {
  sessions: SessionSummary[];
  rooms?: RoomEntry[];
  selectedSessionId: string | null;
  selectedRoomId?: string | null;
  onSelectSession: (session: SessionSummary) => void;
  onSelectRoom?: (room: RoomEntry) => void;
  onNewChat: (agentId?: string) => void;
  onNewRoom?: () => void;
  onDeleteSession?: (session: SessionSummary) => void;
  onDeleteRoom?: (room: RoomEntry) => void;
  search: string;
  onSearchChange: (value: string) => void;
  loading?: boolean;
  error?: string | null;
  unavailable?: boolean;
  onClose?: () => void;
  className?: string;
}

function sortSessionsByRecency(sessions: SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((a, b) => {
    const aTime = a.last_activity_at ? new Date(a.last_activity_at).getTime() : 0;
    const bTime = b.last_activity_at ? new Date(b.last_activity_at).getTime() : 0;
    return bTime - aTime;
  });
}

function SessionRailImpl({
  sessions,
  rooms = [],
  selectedSessionId,
  selectedRoomId = null,
  onSelectSession,
  onSelectRoom,
  onNewChat,
  onNewRoom,
  onDeleteSession,
  onDeleteRoom,
  search,
  onSearchChange,
  loading = false,
  error,
  unavailable = false,
  onClose,
  className,
}: SessionRailProps) {
  const { t } = useAppI18n();
  const { agents, mergeAgents } = useAgentCatalog();
  const agentListRef = useRef<HTMLDivElement | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [agentSearch, setAgentSearch] = useState("");
  const [createMode, setCreateMode] = useState<CreateMode>("conversation");
  const normalizedAgentSearch = agentSearch.trim();

  const newChatAgentsQuery = useInfiniteQuery({
    queryKey: ["control-plane", "agents", "session-new-chat", normalizedAgentSearch],
    queryFn: ({ pageParam }) =>
      fetchAgentCatalogPage({
        search: normalizedAgentSearch,
        offset: Number(pageParam),
        limit: NEW_CHAT_AGENT_PAGE_SIZE,
      }),
    initialPageParam: 0,
    enabled: createOpen && createMode === "conversation",
    staleTime: 10_000,
    refetchOnWindowFocus: false,
    getNextPageParam: (lastPage) =>
      lastPage.has_more && lastPage.items.length > 0
        ? lastPage.offset + lastPage.items.length
        : undefined,
  });

  const newChatAgents = useMemo(
    () => newChatAgentsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [newChatAgentsQuery.data],
  );

  useEffect(() => {
    if (newChatAgents.length > 0) mergeAgents(newChatAgents);
  }, [mergeAgents, newChatAgents]);

  useEffect(() => {
    if (agentListRef.current) agentListRef.current.scrollTop = 0;
  }, [normalizedAgentSearch]);

  const handleCreateOpenChange = (nextOpen: boolean) => {
    setCreateOpen(nextOpen);
    if (!nextOpen) {
      setAgentSearch("");
      setCreateMode("conversation");
    }
  };

  const {
    fetchNextPage,
    hasNextPage,
    isFetching,
    isFetchingNextPage,
  } = newChatAgentsQuery;

  const handleAgentListScroll = useCallback(
    (event: UIEvent<HTMLDivElement>) => {
      const target = event.currentTarget;
      const distanceToBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight;
      if (
        distanceToBottom > NEW_CHAT_AGENT_SCROLL_THRESHOLD ||
        !hasNextPage ||
        isFetchingNextPage
      ) {
        return;
      }
      void fetchNextPage();
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage],
  );

  const isInitialAgentLoading =
    newChatAgentsQuery.isLoading ||
    (newChatAgentsQuery.isFetching && newChatAgents.length === 0);

  const effectiveSearch = search.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!effectiveSearch) return sessions;
    return sessions.filter((session) => {
      const title = (
        session.name ??
        session.latest_query_preview ??
        session.latest_message_preview ??
        ""
      ).toLowerCase();
      return (
        title.includes(effectiveSearch) ||
        session.session_id.toLowerCase().includes(effectiveSearch) ||
        session.bot_id.toLowerCase().includes(effectiveSearch)
      );
    });
  }, [sessions, effectiveSearch]);

  const filteredRooms = useMemo(() => {
    if (!effectiveSearch) return rooms;
    return rooms.filter((entry) => {
      const values = [
        entry.thread.title,
        entry.thread.id,
        entry.thread.squadId,
        entry.squad.squadId,
        entry.squad.coordinatorAgentId,
        entry.thread.coordinatorAgentId,
        entry.thread.currentOwnerAgentId,
        entry.thread.status,
      ];
      return values.some((value) => value?.toLowerCase().includes(effectiveSearch));
    });
  }, [effectiveSearch, rooms]);

  const agentMetaMap = useMemo(() => {
    const map = new Map<string, { label: string; color: string }>();
    for (const agent of agents) {
      const meta = { label: agent.label || agent.id, color: agent.color };
      map.set(agent.id, meta);
      map.set(agent.id.toLowerCase(), meta);
    }
    return map;
  }, [agents]);

  const sortedSessions = useMemo(() => sortSessionsByRecency(filtered), [filtered]);

  const metaForBot = (botId: string) =>
    agentMetaMap.get(botId) ||
    agentMetaMap.get(botId.toLowerCase()) || { label: botId, color: "#A7ADB4" };

  const isSearching = effectiveSearch.length > 0;

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 w-72 shrink-0 flex-col border-r border-[color:var(--border-subtle)] bg-[var(--shell)]",
        "md:w-80",
        className,
      )}
    >
      <div className="flex h-14 shrink-0 items-center justify-between px-3">
        <span className="text-[var(--font-size-sm)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
          {t("chat.rail.title", { defaultValue: "Conversations" })}
        </span>
        <div className="flex items-center gap-1">
          <Popover open={createOpen} onOpenChange={handleCreateOpenChange}>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={t("chat.rail.newSession", { defaultValue: "New conversation" })}
                className={cn(
                  "inline-flex h-8 w-8 items-center justify-center rounded-full",
                  "bg-[var(--panel-strong)] text-[var(--text-primary)]",
                  "transition-[background-color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                  "hover:bg-[var(--surface-hover)] active:scale-[0.96]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
                )}
              >
                <Plus className="icon-sm" strokeWidth={1.75} aria-hidden />
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" sideOffset={8} className="w-72 p-2">
              <div className="flex h-7 gap-0.5 rounded-[var(--radius-pill)] bg-[var(--panel-strong)] p-0.5">
                <button
                  type="button"
                  onClick={() => setCreateMode("conversation")}
                  aria-pressed={createMode === "conversation"}
                  className={cn(
                    "flex-1 rounded-[var(--radius-pill)] text-[0.75rem] font-medium transition-colors duration-[120ms]",
                    createMode === "conversation"
                      ? "bg-[var(--panel)] text-[var(--text-primary)]"
                      : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {t("chat.rail.create.conversation", {
                    defaultValue: "Conversation",
                  })}
                </button>
                <button
                  type="button"
                  onClick={() => setCreateMode("room")}
                  aria-pressed={createMode === "room"}
                  className={cn(
                    "flex-1 rounded-[var(--radius-pill)] text-[0.75rem] font-medium transition-colors duration-[120ms]",
                    createMode === "room"
                      ? "bg-[var(--panel)] text-[var(--text-primary)]"
                      : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {t("chat.rail.create.room", { defaultValue: "Room" })}
                </button>
              </div>
              {createMode === "conversation" ? (
                <>
                  <div className="mb-2 mt-3 px-1 pt-1">
                    <span className="text-[var(--font-size-sm)] font-medium text-[var(--text-secondary)]">
                      {t("chat.rail.newChatAgent", { defaultValue: "Select an agent" })}
                    </span>
                  </div>
                  <label className="mb-2 flex h-8 items-center gap-2 rounded-[calc(var(--radius-input)-4px)] bg-[var(--panel-soft)] px-2.5">
                    <Search className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" strokeWidth={1.75} aria-hidden />
                    <input
                      type="search"
                      value={agentSearch}
                      onChange={(event) => setAgentSearch(event.target.value)}
                      placeholder={t("chat.rail.searchAgents", { defaultValue: "Search agents" })}
                      className="h-full min-w-0 flex-1 bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
                    />
                    {agentSearch ? (
                      <button
                        type="button"
                        onClick={() => setAgentSearch("")}
                        aria-label={t("chat.rail.clearAgentSearch", { defaultValue: "Clear agent search" })}
                        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]"
                      >
                        <X className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                      </button>
                    ) : null}
                  </label>
                  <div
                    ref={agentListRef}
                    className="flex max-h-[300px] min-h-28 flex-col overflow-y-auto"
                    onScroll={handleAgentListScroll}
                    aria-busy={isFetching}
                  >
                    {isInitialAgentLoading ? (
                      <div
                        className="flex h-32 items-center justify-center"
                        aria-label={t("chat.rail.loadingAgents", { defaultValue: "Loading agents" })}
                      >
                        <LoaderCircle className="h-4 w-4 animate-spin text-[var(--text-tertiary)]" strokeWidth={1.75} />
                      </div>
                    ) : newChatAgentsQuery.isError ? (
                      <InlineAlert tone="danger" className="mx-0 my-1">
                        {newChatAgentsQuery.error instanceof Error
                          ? newChatAgentsQuery.error.message
                          : t("chat.rail.agentSearchFailed", { defaultValue: "Could not load agents." })}
                      </InlineAlert>
                    ) : newChatAgents.length === 0 ? (
                      <div className="flex h-28 items-center justify-center px-3 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                        {t("chat.rail.noAgentResults", { defaultValue: "No matching agents" })}
                      </div>
                    ) : (
                      <>
                        {newChatAgents.map((agent) => {
                          const showId =
                            Boolean(agent.label) && agent.label !== agent.id;
                          return (
                            <PopoverClose asChild key={agent.id}>
                              <button
                                type="button"
                                onClick={() => onNewChat(agent.id)}
                                className="flex min-h-9 w-full items-center gap-2 rounded-[var(--radius-panel-sm)] px-1.5 py-1 text-left transition-colors hover:bg-[var(--hover-tint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel)]"
                              >
                                <AgentGlyph
                                  agentId={agent.id}
                                  color={agent.color}
                                  shape="orb"
                                  className="h-6 w-6 shrink-0"
                                />
                                <span className="flex min-w-0 flex-col">
                                  <span className="truncate text-[0.8125rem] font-medium leading-4 text-[var(--text-primary)]">
                                    {agent.label || agent.id}
                                  </span>
                                  {showId ? (
                                    <span className="truncate font-mono text-[0.625rem] leading-3 text-[var(--text-quaternary)]">
                                      {agent.id}
                                    </span>
                                  ) : null}
                                </span>
                              </button>
                            </PopoverClose>
                          );
                        })}
                        {isFetchingNextPage ? (
                          <div
                            className="flex justify-center border-t border-[color:var(--divider-hair)] py-2"
                            aria-label={t("chat.rail.loadingAgents", { defaultValue: "Loading agents" })}
                          >
                            <LoaderCircle className="h-3.5 w-3.5 animate-spin text-[var(--text-quaternary)]" strokeWidth={1.75} />
                          </div>
                        ) : null}
                      </>
                    )}
                  </div>
                </>
              ) : (
                <div className="mt-3 flex flex-col gap-2">
                  <p className="px-2 text-[var(--font-size-sm)] text-[var(--text-secondary)]">
                    {t("chat.rail.create.roomHelper", {
                      defaultValue:
                        "Group multiple agents into a shared room they can collaborate in.",
                    })}
                  </p>
                  <PopoverClose asChild>
                    <button
                      type="button"
                      onClick={() => onNewRoom?.()}
                      disabled={!onNewRoom}
                      className={cn(
                        "flex h-9 items-center justify-center gap-2 rounded-[var(--radius-panel-sm)]",
                        "border border-[color:var(--border-strong)] bg-transparent",
                        "text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]",
                        "transition-colors duration-[120ms] hover:bg-[var(--hover-tint)]",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel)]",
                        "disabled:border-[color:var(--border-subtle)] disabled:text-[var(--text-quaternary)]",
                      )}
                    >
                      <Users className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                      {t("chat.rail.create.openRoomDialog", {
                        defaultValue: "Set up a room…",
                      })}
                    </button>
                  </PopoverClose>
                </div>
              )}
            </PopoverContent>
          </Popover>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label={t("chat.rail.close", { defaultValue: "Close" })}
              className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] md:hidden"
            >
              <X className="icon-sm" strokeWidth={1.75} aria-hidden />
            </button>
          ) : null}
        </div>
      </div>

      <div className="shrink-0 px-3 pb-2 pt-1">
        <RailSearch
          value={search}
          onChange={onSearchChange}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-4 pt-1">
        {loading && sessions.length === 0 && rooms.length === 0 ? (
          <div className="flex flex-col gap-0.5">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="h-12 w-full animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]"
                style={{ animationDelay: `${index * 35}ms` }}
              />
            ))}
          </div>
        ) : error ? (
          <InlineAlert tone="danger" className="mx-0 my-1">
            {error}
          </InlineAlert>
        ) : unavailable ? (
          <InlineAlert tone="warning" className="mx-0 my-1">
            {t("chat.rail.unavailable", {
              defaultValue: "Sessions are not available right now.",
            })}
          </InlineAlert>
        ) : sortedSessions.length === 0 && filteredRooms.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-1.5 px-4 text-center">
            <MessageSquare
              className="icon-lg text-[var(--text-quaternary)]"
              strokeWidth={1.5}
              aria-hidden
            />
            <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
              {isSearching
                ? t("chat.rail.noResults", { defaultValue: "No matching conversations" })
                : t("chat.rail.empty", { defaultValue: "No conversations yet" })}
            </p>
            {!isSearching ? (
              <p className="m-0 text-[0.75rem] text-[var(--text-quaternary)]">
                {t("chat.rail.emptyHelper", { defaultValue: "Press + to start one." })}
              </p>
            ) : null}
          </div>
        ) : (
          <>
            {filteredRooms.length > 0 ? (
              <>
                <div className="px-2.5 pb-1 pt-2 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
                  {t("chat.rail.roomsHeading", { defaultValue: "Rooms" })}
                </div>
                {filteredRooms.map((entry) => (
                  <RoomRow
                    key={entry.thread.id}
                    entry={entry}
                    active={entry.thread.id === selectedRoomId}
                    onSelect={
                      onSelectRoom ? () => onSelectRoom(entry) : () => {}
                    }
                    onRequestDelete={
                      onDeleteRoom ? () => onDeleteRoom(entry) : undefined
                    }
                  />
                ))}
              </>
            ) : null}
            {sortedSessions.length > 0 ? (
              <>
                {filteredRooms.length > 0 ? (
                  <div className="px-2.5 pb-1 pt-3 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
                    {t("chat.rail.sessionsHeading", {
                      defaultValue: "Conversations",
                    })}
                  </div>
                ) : null}
                {sortedSessions.map((session) => {
                  const meta = metaForBot(session.bot_id);
                  return (
                    <SessionRow
                      key={`${session.bot_id}:${session.session_id}`}
                      session={session}
                      agentLabel={meta.label}
                      agentColor={meta.color}
                      active={session.session_id === selectedSessionId}
                      onSelect={() => onSelectSession(session)}
                      onRequestDelete={
                        onDeleteSession ? () => onDeleteSession(session) : undefined
                      }
                    />
                  );
                })}
              </>
            ) : null}
          </>
        )}
      </div>
    </aside>
  );
}

export const SessionRail = memo(SessionRailImpl);
