"use client";

import { memo, type MouseEvent } from "react";
import { Trash2, Users } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { formatRelativeTimestamp } from "@/lib/squads";
import type { RoomEntry } from "@/hooks/use-rooms";
import { cn, truncateText } from "@/lib/utils";

interface RoomRowProps {
  entry: RoomEntry;
  active: boolean;
  onSelect: () => void;
  onRequestDelete?: () => void;
}

function resolveRoomTitle(entry: RoomEntry): string {
  if (entry.thread.title?.trim()) return truncateText(entry.thread.title.trim(), 64);
  return `Room · ${entry.squad.squadId}`;
}

function RoomRowImpl({ entry, active, onSelect, onRequestDelete }: RoomRowProps) {
  const { t } = useAppI18n();
  const title = resolveRoomTitle(entry);
  const time = formatRelativeTimestamp(entry.sortKey);
  const memberLabel = entry.squad.memberCount === 1
    ? t("chat.rail.room.memberSingular", {
        defaultValue: "{{count}} agent",
        count: entry.squad.memberCount,
      })
    : t("chat.rail.room.memberPlural", {
        defaultValue: "{{count}} agents",
        count: entry.squad.memberCount,
      });

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
      data-room-id={entry.thread.id}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className={cn(
          "flex min-w-0 flex-1 items-start gap-2.5 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-left",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
          active
            ? "text-[var(--text-primary)]"
            : "text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]",
        )}
      >
        {entry.thread.photoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={entry.thread.photoUrl}
            alt=""
            aria-hidden
            referrerPolicy="no-referrer"
            className="mt-0.5 h-7 w-7 shrink-0 rounded-full object-cover"
          />
        ) : (
          <span
            aria-hidden
            className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--panel-strong)] text-[var(--text-tertiary)]"
          >
            <Users className="h-3.5 w-3.5" strokeWidth={1.75} />
          </span>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-[var(--font-size-sm)] font-medium leading-[1.3] text-[var(--text-primary)]">
              {title}
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
              {time}
            </span>
          </div>
          <span className="truncate text-[0.75rem] font-light leading-[1.35] text-[var(--text-tertiary)]">
            {memberLabel}
            {entry.thread.coordinatorAgentId
              ? ` · ${entry.thread.coordinatorAgentId}`
              : ""}
          </span>
        </div>
      </button>
      {onRequestDelete ? (
        <button
          type="button"
          onClick={handleDeleteClick}
          aria-label={t("chat.rail.deleteRoom", { defaultValue: "Delete room" })}
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

export const RoomRow = memo(RoomRowImpl);
