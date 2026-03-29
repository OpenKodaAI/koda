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
        tone === "info" && "border-[rgba(120,180,255,0.28)] bg-[rgba(80,136,255,0.12)] text-[rgba(205,226,255,0.94)]",
        tone === "success" && "border-[rgba(122,225,153,0.24)] bg-[rgba(61,155,89,0.14)] text-[rgba(206,245,217,0.96)]",
        tone === "warning" && "border-[rgba(255,204,102,0.28)] bg-[rgba(255,184,77,0.13)] text-[rgba(255,231,184,0.96)]",
        tone === "danger" && "border-[rgba(255,118,118,0.24)] bg-[rgba(173,63,63,0.14)] text-[rgba(255,220,220,0.96)]",
        className,
      )}
    >
      {children}
    </span>
  );
}
