"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type StatusBadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

export function StatusBadge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: StatusBadgeTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.01em]",
        tone === "neutral" && "border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-secondary)]",
        tone === "info" && "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
        tone === "success" && "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
        tone === "warning" && "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
        tone === "danger" && "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
        className,
      )}
    >
      {children}
    </span>
  );
}
