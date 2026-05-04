"use client";

import { StatusDot } from "@/components/ui/status-dot";
import { cn } from "@/lib/utils";
import {
  EXECUTION_TONE_BG,
  EXECUTION_TONE_BORDER,
  EXECUTION_TONE_TEXT,
  executionStatusTone,
  isRunningStatus,
} from "./execution-status";

interface ExecutionStatusPillProps {
  status: string;
  label: string;
  size?: "sm" | "md";
  className?: string;
}

export function ExecutionStatusPill({
  status,
  label,
  size = "sm",
  className,
}: ExecutionStatusPillProps) {
  const tone = executionStatusTone(status);
  const sizeClass =
    size === "md"
      ? "px-2.5 py-1 text-[0.75rem]"
      : "px-2 py-0.5 text-[0.6875rem]";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border font-medium uppercase tracking-[var(--tracking-mono)] whitespace-nowrap",
        sizeClass,
        className,
      )}
      style={{
        background: EXECUTION_TONE_BG[tone],
        borderColor: EXECUTION_TONE_BORDER[tone],
        color: EXECUTION_TONE_TEXT[tone],
      }}
    >
      <StatusDot tone={tone} pulse={isRunningStatus(status)} />
      {label}
    </span>
  );
}
