"use client";

import { memo, type MouseEvent } from "react";
import Image from "next/image";
import { CircleMinus, Hash } from "lucide-react";
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
  const roomPhotoUrl = entry.thread.photoUrl?.trim() || null;
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
        aria-label={`${title}, ${memberLabel}`}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-left",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
          active
            ? "text-[var(--text-primary)]"
            : "text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]",
        )}
      >
        <span
          aria-hidden
          className="relative inline-flex h-7 w-8 shrink-0 items-center justify-center text-[var(--text-tertiary)]"
        >
          {roomPhotoUrl ? (
            <Image
              data-testid="room-row-photo"
              src={roomPhotoUrl}
              alt=""
              width={28}
              height={28}
              unoptimized
              className="h-7 w-7 rounded-[0.45rem] object-cover ring-1 ring-[color:var(--divider-hair)]"
              referrerPolicy="no-referrer"
            />
          ) : (
            <Hash className="h-4 w-4" strokeWidth={1.75} />
          )}
          <span
            className={cn(
              "absolute -right-0.5 top-0 inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-full",
              "bg-[var(--panel-strong)] px-1 font-mono text-[0.5625rem] leading-none text-[var(--text-secondary)]",
              "ring-1 ring-[var(--shell)]",
            )}
          >
            {entry.squad.memberCount}
          </span>
        </span>
        <span className="min-w-0 flex-1 truncate text-[var(--font-size-sm)] font-medium leading-[1.3] text-[var(--text-primary)]">
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
      </button>
      {onRequestDelete ? (
        <button
          type="button"
          onClick={handleDeleteClick}
          aria-label={t("chat.rail.deleteRoom", { defaultValue: "Delete room" })}
          className={cn(
            "absolute right-1.5 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-[var(--radius-panel-sm)]",
            "text-[var(--text-quaternary)] opacity-0 transition-[opacity,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:text-[var(--tone-danger-dot)]",
            "focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--shell)]",
            "group-hover:opacity-100",
          )}
        >
          <CircleMinus className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

export const RoomRow = memo(RoomRowImpl);
