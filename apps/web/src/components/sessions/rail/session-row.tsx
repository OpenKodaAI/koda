"use client";

import { memo, type MouseEvent } from "react";
import { Trash2 } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { SessionSummary } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

interface SessionRowProps {
  session: SessionSummary;
  agentLabel: string;
  agentColor?: string | null;
  active: boolean;
  onSelect: () => void;
  onRequestDelete?: () => void;
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
  if (
    session.latest_status === "retrying" ||
    session.latest_status === "stalled" ||
    session.latest_status === "degraded"
  )
    return { tone: "warning", pulse: true, visible: true };
  return { tone: "neutral", pulse: false, visible: false };
}

function resolvePreview(session: SessionSummary): string {
  if (session.latest_message_preview?.trim())
    return truncateText(session.latest_message_preview.trim(), 64);
  if (session.latest_query_preview?.trim())
    return truncateText(session.latest_query_preview.trim(), 64);
  if (session.name?.trim()) return session.name.trim();
  return `Conversation ${session.session_id.slice(0, 8)}`;
}

function SessionRowImpl({
  session,
  agentLabel,
  agentColor,
  active,
  onSelect,
  onRequestDelete,
}: SessionRowProps) {
  const { t } = useAppI18n();
  const { tone, pulse, visible } = resolveTone(session);
  const preview = resolvePreview(session);
  const timeLabel = relativeShort(session.last_activity_at);

  const handleDeleteClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    event.preventDefault();
    onRequestDelete?.();
  };

  return (
    <div
      role="presentation"
      className={cn(
        "group relative flex w-full items-stretch rounded-[var(--radius-panel-sm)]",
        "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        active
          ? "bg-[var(--panel-strong)]"
          : "hover:bg-[var(--hover-tint)]",
      )}
    >
      <span
        aria-hidden
        className="absolute left-1 top-2 bottom-2 w-1 rounded-full"
        style={{ background: agentColor ?? "#A7ADB4" }}
      />
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={cn(
          "flex min-w-0 flex-1 items-start gap-2.5 rounded-[var(--radius-panel-sm)] py-1.5 pl-4 pr-2 text-left",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
          active
            ? "text-[var(--text-primary)]"
            : "text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]",
        )}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-[var(--font-size-sm)] font-medium leading-[1.3] text-[var(--text-primary)]">
                {agentLabel}
              </span>
              {visible ? (
                <StatusDot tone={tone} pulse={pulse} className="shrink-0" />
              ) : null}
            </span>
            <span
              className={cn(
                "shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)] transition-opacity duration-[120ms]",
                onRequestDelete && "group-hover:opacity-0",
              )}
              aria-label={t("chat.timestamp.lastActivity", {
                defaultValue: "Last activity",
              })}
            >
              {timeLabel}
            </span>
          </div>
          <span className="truncate text-[0.75rem] font-light leading-[1.35] text-[var(--text-tertiary)]">
            {preview}
          </span>
          {session.name?.trim() ? (
            <span className="sr-only">{session.name.trim()}</span>
          ) : null}
        </div>
      </button>
      {onRequestDelete ? (
        <button
          type="button"
          onClick={handleDeleteClick}
          aria-label={t("chat.rail.deleteSession", {
            defaultValue: "Delete conversation",
          })}
          className={cn(
            "absolute right-1.5 top-1.5 inline-flex h-6 w-6 items-center justify-center rounded-[var(--radius-panel-sm)]",
            "text-[var(--text-quaternary)] opacity-0 transition-[opacity,color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:bg-[var(--tone-danger-bg)] hover:text-[var(--tone-danger-dot)]",
            "focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
            "group-hover:opacity-100",
          )}
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

export const SessionRow = memo(SessionRowImpl);
