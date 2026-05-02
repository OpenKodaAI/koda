"use client";

import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TriggerTileProps {
  icon: LucideIcon;
  title: string;
  description: string;
  selected?: boolean;
  disabled?: boolean;
  hint?: string;
  onClick?: () => void;
}

export function TriggerTile({
  icon: Icon,
  title,
  description,
  selected = false,
  disabled = false,
  hint,
  onClick,
}: TriggerTileProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-disabled={disabled || undefined}
      disabled={disabled}
      onClick={() => {
        if (!disabled) onClick?.();
      }}
      className={cn(
        "group relative flex w-full items-start gap-3 rounded-[var(--radius-panel)] border bg-[var(--panel-soft)] px-4 py-3 text-left",
        "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel)]",
        selected
          ? "border-[var(--accent)] bg-[var(--panel)]"
          : "border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]",
        disabled && "cursor-not-allowed opacity-55 hover:border-[var(--border-subtle)] hover:bg-[var(--panel-soft)]",
      )}
    >
      <span
        className={cn(
          "mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-secondary)]",
          selected && "border-[var(--accent)] text-[var(--accent)]",
        )}
        aria-hidden
      >
        <Icon className="icon-sm" strokeWidth={1.75} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-[0.875rem] font-medium text-[var(--text-primary)]">{title}</span>
        <span className="text-[0.8125rem] text-[var(--text-tertiary)]">{description}</span>
      </span>
      {hint ? (
        <span className="ml-3 self-start font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          {hint}
        </span>
      ) : null}
    </button>
  );
}
