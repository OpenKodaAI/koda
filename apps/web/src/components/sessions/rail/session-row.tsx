"use client";

import { memo } from "react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { SessionSummary } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

interface SessionRowProps {
  session: SessionSummary;
  active: boolean;
  onSelect: () => void;
  index?: number;
}

function relativeShort(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 60_000) return "now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function resolveTone(session: SessionSummary): {
  tone: StatusDotTone;
  pulse: boolean;
  visible: boolean;
} {
  if (session.running_count > 0) return { tone: "accent", pulse: true, visible: true };
  if (session.failed_count > 0) return { tone: "danger", pulse: false, visible: true };
  if (session.latest_status === "retrying")
    return { tone: "warning", pulse: true, visible: true };
  return { tone: "neutral", pulse: false, visible: false };
}

function resolveTitle(session: SessionSummary): string {
  if (session.name?.trim()) return session.name.trim();
  if (session.latest_query_preview?.trim())
    return truncateText(session.latest_query_preview.trim(), 48);
  if (session.latest_message_preview?.trim())
    return truncateText(session.latest_message_preview.trim(), 48);
  return `Conversation ${session.session_id.slice(0, 8)}`;
}

function SessionRowImpl({ session, active, onSelect, index }: SessionRowProps) {
  const { t } = useAppI18n();
  const { tone, pulse, visible } = resolveTone(session);
  const title = resolveTitle(session);
  const timeLabel = relativeShort(session.last_activity_at);
  const staggerDelay = typeof index === "number" ? Math.min(index, 8) * 18 : 0;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      style={staggerDelay > 0 ? { animationDelay: `${staggerDelay}ms` } : undefined}
      className={cn(
        "group relative flex h-9 w-full items-center gap-2 rounded-[var(--radius-panel-sm)] px-2.5 text-left",
        "animate-in fade-in-0 slide-in-from-left-1 duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
        active
          ? "bg-[var(--hover-tint)] font-medium text-[var(--text-primary)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
      )}
    >
      {active ? (
        <span
          aria-hidden
          className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-[var(--accent)]"
        />
      ) : null}
      {visible ? <StatusDot tone={tone} pulse={pulse} /> : null}
      <span className="min-w-0 flex-1 truncate text-[var(--font-size-sm)] leading-[1.3]">
        {title}
      </span>
      <span
        className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]"
        aria-label={t("chat.timestamp.lastActivity", {
          defaultValue: "Last activity",
        })}
      >
        {timeLabel}
      </span>
    </button>
  );
}

export const SessionRow = memo(SessionRowImpl);
