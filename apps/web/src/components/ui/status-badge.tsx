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
        "inline-flex min-h-[24px] items-center gap-1.5 rounded-[var(--radius-chip)] px-2 py-0.5 text-[10.5px] font-semibold tracking-[var(--tracking-mono)] uppercase",
        tone === "neutral" && "bg-[var(--panel-soft)] text-[color:var(--text-secondary)]",
        tone === "info" && "bg-[var(--tone-info-bg)] text-[color:var(--tone-info-text)]",
        tone === "success" && "bg-[var(--tone-success-bg)] text-[color:var(--tone-success-text)]",
        tone === "warning" && "bg-[var(--tone-warning-bg)] text-[color:var(--tone-warning-text)]",
        tone === "danger" && "bg-[var(--tone-danger-bg)] text-[color:var(--tone-danger-text)]",
        className,
      )}
    >
      {children}
    </span>
  );
}
