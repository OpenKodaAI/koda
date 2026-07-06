"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { StatusDot } from "@/components/ui/status-dot";
import { cn } from "@/lib/utils";

export type EventLevel = "info" | "warn" | "error" | "debug" | "success";

interface EventRowProps {
  level?: EventLevel;
  timestamp?: string;
  message: ReactNode;
  source?: ReactNode;
  payload?: unknown;
  className?: string;
}

const LEVEL_TONE: Record<EventLevel, React.ComponentProps<typeof StatusDot>["tone"]> = {
  info: "info",
  warn: "warning",
  error: "danger",
  debug: "neutral",
  success: "success",
};

function formatTime(iso?: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function EventRow({
  level = "info",
  timestamp,
  message,
  source,
  payload,
  className,
}: EventRowProps) {
  const [expanded, setExpanded] = useState(false);
  const hasPayload = payload !== undefined && payload !== null;
  const time = formatTime(timestamp);

  return (
    <article
      className={cn(
        "grid w-full gap-2 border-b border-[color:var(--divider-hair)] py-2 text-[0.8125rem] last:border-b-0",
        "grid-cols-[auto_auto_1fr_auto] items-start",
        className,
      )}
    >
      <StatusDot tone={LEVEL_TONE[level]} className="mt-[6px]" />
      <span className="font-mono text-[0.6875rem] leading-[1.35] text-[var(--text-quaternary)] pt-0.5">
        {time}
      </span>
      <div className="min-w-0">
        <p className="m-0 truncate text-[var(--text-secondary)]">{message}</p>
        {source ? (
          <p className="m-0 text-[0.6875rem] text-[var(--text-quaternary)]">{source}</p>
        ) : null}
        {hasPayload && expanded ? (
          <pre className="mt-1.5 max-h-40 overflow-auto rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-2 font-mono text-[0.6875rem] leading-[1.5] text-[var(--text-tertiary)]">
            {typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)}
          </pre>
        ) : null}
      </div>
      {hasPayload ? (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
          className={cn(
            "inline-flex h-6 w-6 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-quaternary)] transition-[color,transform,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]",
            expanded && "rotate-180",
          )}
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      ) : <span />}
    </article>
  );
}
