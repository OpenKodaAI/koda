"use client";

import * as React from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface AvatarGroupItem {
  id: string;
  name: string;
  initials?: string | null;
  color?: string | null;
  imageUrl?: string | null;
}

interface AvatarGroupWithTooltipsProps {
  avatars: AvatarGroupItem[];
  maxVisible?: number;
  size?: "xs" | "sm" | "md";
  appearance?: "bare" | "pill";
  showInitials?: boolean;
  ariaLabel?: string;
  className?: string;
}

const sizeClasses = {
  xs: {
    avatar: "h-[22px] w-[22px] text-[0.5625rem]",
    overlap: "-ml-1.5",
    shell: "p-0",
  },
  sm: {
    avatar: "h-6 w-6 text-[0.625rem]",
    overlap: "-ml-2",
    shell: "p-0.5",
  },
  md: {
    avatar: "h-7 w-7 text-[0.6875rem]",
    overlap: "-ml-2",
    shell: "p-1",
  },
} as const;

function normalizeInitials(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function getAvatarGroupInitials(item: AvatarGroupItem): string {
  const explicit = item.initials?.trim();
  if (explicit) return explicit.slice(0, 2).toUpperCase();
  const normalized = normalizeInitials(item.name || item.id);
  if (normalized.length >= 2) return normalized;
  const compact = (item.name || item.id).replace(/[\s_-]+/g, "");
  return compact.slice(0, 2).toUpperCase() || item.id.slice(0, 2).toUpperCase();
}

function readableTextColor(background: string | null | undefined): string {
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

function uniqueAvatarItems(items: AvatarGroupItem[]): AvatarGroupItem[] {
  const seen = new Set<string>();
  const unique: AvatarGroupItem[] = [];
  for (const item of items) {
    const id = item.id.trim();
    if (!id || seen.has(id.toLowerCase())) continue;
    seen.add(id.toLowerCase());
    unique.push({ ...item, id, name: item.name.trim() || id });
  }
  return unique;
}

export function AvatarGroupWithTooltips({
  avatars,
  maxVisible = 4,
  size = "sm",
  appearance = "bare",
  showInitials = true,
  ariaLabel = "Participants",
  className,
}: AvatarGroupWithTooltipsProps) {
  const uniqueAvatars = uniqueAvatarItems(avatars);
  if (uniqueAvatars.length === 0) return null;

  const visibleCount = Math.max(1, maxVisible);
  const visible = uniqueAvatars.slice(0, visibleCount);
  const overflow = uniqueAvatars.slice(visibleCount);
  const classes = sizeClasses[size];
  const shellClass =
    appearance === "pill"
      ? "inline-flex max-w-full items-center rounded-full border border-[color:var(--divider-hair)] bg-[var(--panel-soft)]/80"
      : "inline-flex max-w-full items-center";

  return (
    <TooltipProvider delayDuration={250}>
      <div
        className={cn(shellClass, classes.shell, className)}
        aria-label={ariaLabel}
      >
        <div className="flex min-w-0 items-center">
          {visible.map((avatar, index) => (
            <Tooltip key={avatar.id}>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    "relative inline-flex shrink-0 rounded-full",
                    index > 0 && classes.overlap,
                  )}
                  aria-label={avatar.name}
                >
                  <Avatar
                    className={cn(
                      "overflow-hidden rounded-full border border-[color:var(--canvas)] bg-[var(--panel-strong)] ring-1 ring-[color:var(--divider-hair)] transition-colors hover:border-[color:var(--border-strong)]",
                      classes.avatar,
                    )}
                  >
                    {avatar.imageUrl ? (
                      <AvatarImage src={avatar.imageUrl} alt={avatar.name} className="h-full w-full" />
                    ) : null}
                    <AvatarFallback
                      className="border-0 font-medium tracking-[-0.01em]"
                      style={{
                        backgroundColor: avatar.color ?? "var(--panel-strong)",
                        color: readableTextColor(avatar.color),
                      }}
                    >
                      {showInitials ? getAvatarGroupInitials(avatar) : null}
                    </AvatarFallback>
                  </Avatar>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="font-medium">
                {avatar.name}
              </TooltipContent>
            </Tooltip>
          ))}
          {overflow.length > 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    "relative inline-flex shrink-0 items-center justify-center rounded-full border border-[color:var(--canvas)] bg-[var(--panel-strong)] font-mono font-medium text-[var(--text-secondary)] ring-1 ring-[color:var(--divider-hair)] transition-colors hover:border-[color:var(--border-strong)]",
                    classes.avatar,
                    visible.length > 0 && classes.overlap,
                  )}
                  aria-label={`${overflow.length} more participants`}
                >
                  +{overflow.length}
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="font-medium">
                {overflow.map((item) => item.name).join(", ")}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </div>
    </TooltipProvider>
  );
}
