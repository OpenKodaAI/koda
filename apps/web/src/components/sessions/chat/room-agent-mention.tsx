"use client";

import { X } from "lucide-react";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

export interface RoomAgentMentionMeta {
  id: string;
  label: string;
  color: string | null;
}

export type RoomMentionSegment =
  | { kind: "text"; text: string }
  | { kind: "mention"; mention: RoomAgentMentionMeta; raw: string };

const MENTION_RE = /(^|[^A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_.-]*)/g;
const SAFE_MENTION_TOKEN_RE = /^[A-Za-z][A-Za-z0-9_.-]*$/;

export function roomAgentMentionToken(mention: RoomAgentMentionMeta): string {
  const label = mention.label.trim();
  if (SAFE_MENTION_TOKEN_RE.test(label)) return label;
  return mention.id;
}

export function roomAgentMentionLiteral(mention: RoomAgentMentionMeta): string {
  return `@${roomAgentMentionToken(mention)}`;
}

export function splitRoomAgentMentions(
  text: string,
  mentionsByToken: ReadonlyMap<string, RoomAgentMentionMeta>,
): RoomMentionSegment[] {
  if (!text) return [];
  const segments: RoomMentionSegment[] = [];
  let lastIndex = 0;
  MENTION_RE.lastIndex = 0;

  for (const match of text.matchAll(MENTION_RE)) {
    const prefix = match[1] ?? "";
    const token = match[2] ?? "";
    const mentionStart = match.index + prefix.length;
    const mentionEnd = mentionStart + token.length + 1;
    const mention = mentionsByToken.get(token.toLowerCase());
    if (!mention) continue;

    if (mentionStart > lastIndex) {
      segments.push({ kind: "text", text: text.slice(lastIndex, mentionStart) });
    }
    segments.push({ kind: "mention", mention, raw: text.slice(mentionStart, mentionEnd) });
    lastIndex = mentionEnd;
  }

  if (lastIndex < text.length) {
    segments.push({ kind: "text", text: text.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ kind: "text", text }];
}

export function extractRoomAgentMentionIds(
  text: string,
  mentionsByToken: ReadonlyMap<string, RoomAgentMentionMeta>,
): string[] {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const segment of splitRoomAgentMentions(text, mentionsByToken)) {
    if (segment.kind !== "mention") continue;
    const key = segment.mention.id.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    ids.push(segment.mention.id);
  }
  return ids;
}

export function RoomAgentMentionBadge({
  mention,
  onRemove,
  className,
}: {
  mention: RoomAgentMentionMeta;
  onRemove?: (mention: RoomAgentMentionMeta) => void;
  className?: string;
}) {
  const accentColor = mention.color?.trim() || null;
  const accentStyle = accentColor
    ? ({
        "--agent-mention-bg": `color-mix(in srgb, ${accentColor} 14%, transparent)`,
        "--agent-mention-border": `color-mix(in srgb, ${accentColor} 28%, var(--border-subtle))`,
        "--agent-mention-text": `color-mix(in srgb, ${accentColor} 74%, var(--text-primary))`,
      } as CSSProperties)
    : undefined;
  return (
    <span
      className={cn(
        "inline-flex h-6 max-w-[14rem] items-center gap-1 align-middle",
        "rounded-[var(--radius-pill)] border shadow-[var(--shadow-xs)]",
        accentColor
          ? "border-[color:var(--agent-mention-border)] bg-[var(--agent-mention-bg)] text-[var(--agent-mention-text)]"
          : "border-[color:var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--tone-info-dot)]",
        "px-2 text-[0.75rem] font-medium leading-none",
        className,
      )}
      data-agent-mention={mention.id}
      style={accentStyle}
    >
      <span className="min-w-0 truncate tracking-[-0.005em]">@{mention.label}</span>
      {onRemove ? (
        <button
          type="button"
          onClick={() => onRemove(mention)}
          className="ml-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]"
          aria-label={`Remove @${mention.label}`}
        >
          <X className="h-2.5 w-2.5" strokeWidth={2} aria-hidden />
        </button>
      ) : null}
    </span>
  );
}

export function RoomMentionRichText({
  text,
  mentionsByToken,
  variant = "badge",
}: {
  text: string;
  mentionsByToken: ReadonlyMap<string, RoomAgentMentionMeta>;
  variant?: "badge" | "inline";
}) {
  const segments = splitRoomAgentMentions(text, mentionsByToken);
  return (
    <>
      {segments.map((segment, index) => {
        if (segment.kind === "text") {
          return <span key={`text-${index}`}>{segment.text}</span>;
        }
        if (variant === "inline") {
          return (
            <span
              key={`mention-${segment.mention.id}-${index}`}
              className="font-medium text-[var(--tone-info-dot)]"
            >
              {segment.raw}
            </span>
          );
        }
        return (
          <RoomAgentMentionBadge
            key={`mention-${segment.mention.id}-${index}`}
            mention={segment.mention}
            className="mx-0.5 translate-y-[-1px]"
          />
        );
      })}
    </>
  );
}
