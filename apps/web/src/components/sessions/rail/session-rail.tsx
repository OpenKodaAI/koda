"use client";

import { memo, useMemo, useState } from "react";
import { MessageSquare, Plus, X } from "lucide-react";
import { SessionGroup } from "@/components/sessions/rail/session-group";
import { SessionRow } from "@/components/sessions/rail/session-row";
import { RailSearch } from "@/components/sessions/rail/rail-search";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { SessionSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SessionRailProps {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  onSelectSession: (session: SessionSummary) => void;
  onNewChat: () => void;
  search: string;
  onSearchChange: (value: string) => void;
  loading?: boolean;
  error?: string | null;
  unavailable?: boolean;
  onClose?: () => void;
  className?: string;
}

interface GroupEntry {
  id: string;
  label: string;
  sessions: SessionSummary[];
}

function groupSessionsByAgent(
  sessions: SessionSummary[],
  labelFor: (agentId: string) => string,
): GroupEntry[] {
  const map = new Map<string, GroupEntry>();
  for (const session of sessions) {
    const id = session.bot_id;
    const existing = map.get(id);
    if (existing) {
      existing.sessions.push(session);
      continue;
    }
    map.set(id, { id, label: labelFor(id), sessions: [session] });
  }
  for (const entry of map.values()) {
    entry.sessions.sort((a, b) => {
      const aTime = a.last_activity_at ? new Date(a.last_activity_at).getTime() : 0;
      const bTime = b.last_activity_at ? new Date(b.last_activity_at).getTime() : 0;
      return bTime - aTime;
    });
  }
  return [...map.values()].sort((a, b) => {
    const aLatest = a.sessions[0]?.last_activity_at
      ? new Date(a.sessions[0].last_activity_at).getTime()
      : 0;
    const bLatest = b.sessions[0]?.last_activity_at
      ? new Date(b.sessions[0].last_activity_at).getTime()
      : 0;
    return bLatest - aLatest;
  });
}

function SessionRailImpl({
  sessions,
  selectedSessionId,
  onSelectSession,
  onNewChat,
  search,
  onSearchChange,
  loading = false,
  error,
  unavailable = false,
  onClose,
  className,
}: SessionRailProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [localSearch, setLocalSearch] = useState(search);

  const effectiveSearch = localSearch.trim().toLowerCase();
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

  const agentLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.id, agent.label || agent.id);
      map.set(agent.id.toLowerCase(), agent.label || agent.id);
    }
    return map;
  }, [agents]);

  const groups = useMemo(
    () =>
      groupSessionsByAgent(filtered, (agentId) =>
        agentLabelMap.get(agentId) || agentLabelMap.get(agentId.toLowerCase()) || agentId,
      ),
    [filtered, agentLabelMap],
  );

  const isSearching = effectiveSearch.length > 0;

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 w-72 shrink-0 flex-col border-r border-[color:var(--border-subtle)] bg-[var(--shell)]",
        className,
      )}
    >
      <div className="flex h-14 shrink-0 items-center justify-between px-3">
        <span className="text-[var(--font-size-sm)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
          {t("chat.rail.title", { defaultValue: "Conversations" })}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onNewChat}
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
          value={localSearch}
          onChange={(value) => {
            setLocalSearch(value);
            onSearchChange(value);
          }}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3 pb-4 pt-1">
        {loading && sessions.length === 0 ? (
          <div className="flex flex-col gap-0.5">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="h-9 w-full animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]"
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
        ) : groups.length === 0 ? (
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
          groups.map((group) => (
            <SessionGroup key={group.id} label={group.label}>
              {group.sessions.map((session, index) => (
                <SessionRow
                  key={`${session.bot_id}:${session.session_id}`}
                  session={session}
                  active={session.session_id === selectedSessionId}
                  onSelect={() => onSelectSession(session)}
                  index={index}
                />
              ))}
            </SessionGroup>
          ))
        )}
      </div>
    </aside>
  );
}

export const SessionRail = memo(SessionRailImpl);
