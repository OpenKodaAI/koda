"use client";

import { useMemo } from "react";
import { LoaderCircle, MessageSquarePlus, Search, X } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { ErrorState } from "@/components/ui/async-feedback";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { getBotColor } from "@/lib/bot-constants";
import type { SessionSummary } from "@/lib/types";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";

const DEFAULT_RAIL_SESSION_LIMIT = 3;
const DEFAULT_RAIL_FRAGMENT_EXECUTIONS = 3;

function shouldDisplaySessionInRail(session: SessionSummary) {
  if (session.query_count > 0) return true;
  if (session.running_count > 0) return true;
  if (session.failed_count > 0) return true;
  if (session.execution_count >= DEFAULT_RAIL_FRAGMENT_EXECUTIONS) return true;
  if (session.latest_response_preview?.trim()) return true;
  if (session.name?.trim()) return true;
  return false;
}

function ConversationRailSkeleton() {
  return (
    <div>
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="skeleton mx-2 my-0.5 h-[60px] rounded-[0.8rem]" />
      ))}
    </div>
  );
}

function RailConversationRow({
  session,
  selected,
  loading,
  onClick,
  botLabel,
}: {
  session: SessionSummary;
  selected: boolean;
  loading: boolean;
  onClick: () => void;
  botLabel: string;
}) {
  const preview = truncateText(
    session.latest_message_preview ||
      session.latest_response_preview ||
      session.latest_query_preview ||
      (session.name && session.name !== botLabel ? session.name : null) ||
      `Conversation ${session.session_id.slice(0, 8)}` ||
      "",
    72,
  );
  const title = session.name?.trim() || botLabel;
  const metaLabel = session.name?.trim() ? botLabel : null;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-busy={loading}
      className={cn(
        "flex min-h-[3.65rem] w-full items-center gap-3 rounded-[0.95rem] px-3 py-2 text-left transition-[background-color,transform,opacity] duration-180 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-1px] focus-visible:outline-[var(--border-strong)]",
        selected
          ? "bg-[var(--selection-bg)]"
          : "hover:bg-[var(--surface-panel-soft)]",
        loading && "opacity-90",
      )}
    >
      <BotAgentGlyph
        botId={session.bot_id}
        color={getBotColor(session.bot_id)}
        active={selected}
        variant="list"
        shape="swatch"
        className="h-10 w-10 shrink-0 bot-swatch--animated"
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 truncate pr-2">
            <p className="truncate text-[13px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
              {title}
              {metaLabel ? (
                <span className="ml-1.5 text-[11px] font-normal tracking-normal text-[var(--text-quaternary)]">
                  {`· ${metaLabel}`}
                </span>
              ) : null}
            </p>
          </div>
          {loading ? (
            <span className="inline-flex shrink-0 items-center gap-1.5 pt-0.5 text-[10px] text-[var(--text-quaternary)]">
              <LoaderCircle className="h-3 w-3 animate-spin" />
              Loading
            </span>
          ) : (
            <span className="shrink-0 pt-0.5 text-[10px] text-[var(--text-quaternary)]">
              {session.last_activity_at ? formatRelativeTime(session.last_activity_at) : ""}
            </span>
          )}
        </div>
        {preview && (
          <p className="mt-0.5 truncate text-[12px] leading-5 text-[var(--text-secondary)]">
            {preview}
          </p>
        )}
      </div>
    </button>
  );
}

interface SessionConversationRailProps {
  search: string;
  onSearchChange: (value: string) => void;
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  loading: boolean;
  refreshing?: boolean;
  loadingSessionId?: string | null;
  error?: string | null;
  unavailable?: boolean;
  onRefresh: () => void;
  onSelectSession: (session: SessionSummary) => void;
  onNewChat: () => void;
  className?: string;
  onClose?: () => void;
}

export function SessionConversationRail({
  search,
  onSearchChange,
  sessions,
  selectedSessionId,
  loading,
  refreshing = false,
  loadingSessionId = null,
  error,
  unavailable = false,
  onRefresh,
  onSelectSession,
  onNewChat,
  className,
  onClose,
}: SessionConversationRailProps) {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const botLabelMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const bot of bots) {
      map[bot.id] = bot.label || bot.id;
      map[bot.id.toLowerCase()] = bot.label || bot.id;
    }
    return map;
  }, [bots]);
  const displayedSessions = useMemo(() => {
    if (search.trim()) {
      return sessions;
    }

    const meaningful = sessions.filter(shouldDisplaySessionInRail);

    if (selectedSessionId) {
      const selected = sessions.find((session) => session.session_id === selectedSessionId);
      const remainder = meaningful.filter(
        (session) => session.session_id !== selectedSessionId,
      );
      if (selected && !shouldDisplaySessionInRail(selected)) {
        return [selected, ...remainder.slice(0, DEFAULT_RAIL_SESSION_LIMIT - 1)];
      }
    }

    if (meaningful.length > 0) {
      return meaningful.slice(0, DEFAULT_RAIL_SESSION_LIMIT);
    }

    return sessions.slice(0, Math.min(DEFAULT_RAIL_SESSION_LIMIT, sessions.length));
  }, [search, selectedSessionId, sessions]);

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-canvas)]",
        className
      )}
    >
      <div
        className="border-b border-[var(--border-subtle)] px-4 py-4"
        {...tourAnchor("sessions.rail-header")}
      >
        {onClose ? (
          <div className="mb-3 flex justify-end lg:hidden">
            <button
              type="button"
              onClick={onClose}
              className="button-shell button-shell--secondary button-shell--icon h-10 w-10 text-[var(--text-secondary)]"
              aria-label={t("sessions.rail.close")}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : null}

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <label className="app-search min-w-0 flex-1">
              <Search className="h-4 w-4 text-[var(--text-quaternary)]" />
              <input
                type="text"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={t("sessions.rail.searchPlaceholder")}
              />
            </label>

            <button
              type="button"
              onClick={onNewChat}
              className="button-shell button-shell--secondary button-shell--icon h-11 w-11 shrink-0 text-[var(--text-secondary)]"
              aria-label={t("sessions.rail.newChat", { defaultValue: "New chat" })}
              title={t("sessions.rail.newChat", { defaultValue: "New chat" })}
            >
              <MessageSquarePlus className="h-4 w-4" />
            </button>
          </div>

          {refreshing ? (
            <div className="flex items-center gap-2 px-1 text-[11px] text-[var(--text-tertiary)]">
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              <span>{t("sessions.rail.refreshing", { defaultValue: "Refreshing conversations..." })}</span>
            </div>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-1.5">
        {loading && displayedSessions.length === 0 ? (
          <ConversationRailSkeleton />
        ) : error ? (
          <ErrorState title={t("sessions.rail.loadError")} description={error} onRetry={onRefresh} />
        ) : unavailable ? (
          <div className="empty-state min-h-[18rem]">
            <p className="empty-state-text">{t("sessions.rail.unavailable")}</p>
            <p className="empty-state-subtext">{t("sessions.rail.unavailableDescription")}</p>
          </div>
        ) : displayedSessions.length === 0 ? (
          <div className="empty-state min-h-[18rem]">
            <p className="empty-state-text">{t("sessions.rail.noResults")}</p>
            <p className="empty-state-subtext">{t("sessions.rail.noResultsDescription")}</p>
          </div>
        ) : (
          <div>
            {displayedSessions.map((session) => (
              <RailConversationRow
                key={`${session.bot_id}:${session.session_id}`}
                session={session}
                selected={session.session_id === selectedSessionId}
                loading={session.session_id === loadingSessionId}
                onClick={() => onSelectSession(session)}
                botLabel={
                  botLabelMap[session.bot_id] ||
                  botLabelMap[session.bot_id.toLowerCase()] ||
                  session.bot_id
                }
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
