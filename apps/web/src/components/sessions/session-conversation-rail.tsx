"use client";

import { MessageSquarePlus, Search, X } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { ErrorState } from "@/components/ui/async-feedback";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor } from "@/lib/bot-constants";
import type { SessionSummary } from "@/lib/types";
import { cn, formatRelativeTime, truncateText } from "@/lib/utils";

function sessionStatusLabel(session: SessionSummary) {
  if (session.running_count > 0) return "running";
  if (session.failed_count > 0) return "failed";
  return session.latest_status ?? "completed";
}

function ConversationRailSkeleton() {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="skeleton h-[78px] w-full rounded-[1rem]" />
      ))}
    </div>
  );
}

function RailConversationRow({
  session,
  selected,
  onClick,
}: {
  session: SessionSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const status = sessionStatusLabel(session);
  const { t } = useAppI18n();

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-[1rem] border px-3.5 py-3 text-left transition-[background-color,border-color] duration-200",
        selected
          ? "border-[rgba(126,132,255,0.18)] bg-[rgba(255,255,255,0.05)]"
          : "border-transparent bg-transparent hover:border-[rgba(255,255,255,0.06)] hover:bg-[rgba(255,255,255,0.03)]"
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[1rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.028)]">
        <BotAgentGlyph
          botId={session.bot_id}
          color={getBotColor(session.bot_id)}
          active={selected}
          variant="list"
          shape="swatch"
          className="h-6 w-6"
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium tracking-[-0.03em] text-[var(--text-primary)]">
              {session.name || truncateText(session.session_id, 28)}
            </p>
            <p className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">
              {session.latest_message_preview || t("sessions.rail.noMessages")}
            </p>
          </div>

          <div className="shrink-0 text-right">
            <p className="text-[11px] text-[var(--text-tertiary)]">
              {session.last_activity_at ? formatRelativeTime(session.last_activity_at) : "—"}
            </p>
          </div>
        </div>

        <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--text-quaternary)]">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-[var(--text-quaternary)]" />
          <span>{status}</span>
          <span>•</span>
          <span>{session.query_count} msgs</span>
        </div>
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
  error,
  unavailable = false,
  onRefresh,
  onSelectSession,
  onNewChat,
  className,
  onClose,
}: SessionConversationRailProps) {
  const { t } = useAppI18n();

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 flex-col border-r border-[rgba(255,255,255,0.06)] bg-[#0d0e12]",
        className
      )}
    >
      <div
        className="border-b border-[rgba(255,255,255,0.06)] px-4 py-4"
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
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {loading && sessions.length === 0 ? (
          <ConversationRailSkeleton />
        ) : error ? (
          <ErrorState title={t("sessions.rail.loadError")} description={error} onRetry={onRefresh} />
        ) : unavailable ? (
          <div className="empty-state min-h-[18rem]">
            <p className="empty-state-text">{t("sessions.rail.unavailable")}</p>
            <p className="empty-state-subtext">{t("sessions.rail.unavailableDescription")}</p>
          </div>
        ) : sessions.length === 0 ? (
          <div className="empty-state min-h-[18rem]">
            <p className="empty-state-text">{t("sessions.rail.noResults")}</p>
            <p className="empty-state-subtext">{t("sessions.rail.noResultsDescription")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <RailConversationRow
                key={`${session.bot_id}:${session.session_id}`}
                session={session}
                selected={session.session_id === selectedSessionId}
                onClick={() => onSelectSession(session)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
