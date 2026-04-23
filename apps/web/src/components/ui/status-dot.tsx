"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";

export type StatusDotTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "accent"
  | "retry";

export interface StatusDotProps {
  tone?: StatusDotTone;
  color?: string;
  size?: "sm" | "md";
  pulse?: boolean;
  className?: string;
}

const TONE_VAR: Record<StatusDotTone, string> = {
  neutral: "var(--tone-neutral-dot)",
  info: "var(--tone-info-dot)",
  success: "var(--tone-success-dot)",
  warning: "var(--tone-warning-dot)",
  danger: "var(--tone-danger-dot)",
  retry: "var(--tone-retry-dot)",
  accent: "var(--accent)",
};

export const StatusDot = memo(function StatusDot({
  tone = "neutral",
  color,
  size = "sm",
  pulse = false,
  className,
}: StatusDotProps) {
  const dotSize = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";
  const background = color ?? TONE_VAR[tone];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block shrink-0 rounded-full",
        dotSize,
        pulse && "animate-[agent-pulse_1.6s_ease-in-out_infinite]",
        className,
      )}
      style={{ background }}
    />
  );
});
