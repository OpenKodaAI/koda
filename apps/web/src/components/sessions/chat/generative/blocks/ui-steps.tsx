"use client";

import { Check, Circle, AlertCircle, MinusCircle, Loader2 } from "lucide-react";
import { StatusDot } from "@/components/ui/status-dot";
import type { z } from "zod";
import type { uiStepsBlockSchema } from "@/lib/contracts/generative-ui";

export type UiStepsBlock = z.infer<typeof uiStepsBlockSchema>;

type StepStatus = UiStepsBlock["payload"]["items"][number]["status"];

const STATUS_TONE: Record<
  StepStatus,
  "neutral" | "info" | "success" | "warning" | "danger"
> = {
  pending: "neutral",
  running: "info",
  done: "success",
  failed: "danger",
  skipped: "warning",
};

interface StatusGlyphProps {
  status: StepStatus;
}

function StatusGlyph({ status }: StatusGlyphProps) {
  switch (status) {
    case "running":
      return (
        <Loader2
          className="h-3.5 w-3.5 shrink-0 animate-spin text-[var(--tone-info-dot)]"
          strokeWidth={1.75}
          aria-hidden
        />
      );
    case "done":
      return (
        <Check
          className="h-3.5 w-3.5 shrink-0 text-[var(--tone-success-dot)]"
          strokeWidth={2}
          aria-hidden
        />
      );
    case "failed":
      return (
        <AlertCircle
          className="h-3.5 w-3.5 shrink-0 text-[var(--tone-danger-dot)]"
          strokeWidth={1.75}
          aria-hidden
        />
      );
    case "skipped":
      return (
        <MinusCircle
          className="h-3.5 w-3.5 shrink-0 text-[var(--tone-warning-dot)]"
          strokeWidth={1.75}
          aria-hidden
        />
      );
    case "pending":
    default:
      return (
        <Circle
          className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]"
          strokeWidth={1.75}
          aria-hidden
        />
      );
  }
}

export function UiSteps({ block }: { block: UiStepsBlock }) {
  const { title, items } = block.payload;

  return (
    <div className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] py-1">
      {title ? (
        <h4 className="m-0 px-3 pt-2 pb-1 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
          {title}
        </h4>
      ) : null}
      <ol className="m-0 list-none p-0">
        {items.map((step) => (
          <li
            key={step.id}
            className="grid grid-cols-[auto_1fr_auto] items-center gap-2.5 border-b border-[color:var(--divider-hair)] px-3 py-2 last:border-b-0"
          >
            <StatusGlyph status={step.status} />
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[0.875rem] text-[var(--text-primary)]">
                {step.label}
              </span>
              {step.detail ? (
                <span className="truncate text-[0.75rem] text-[var(--text-tertiary)]">
                  {step.detail}
                </span>
              ) : null}
            </div>
            <StatusDot
              tone={STATUS_TONE[step.status]}
              pulse={step.status === "running"}
            />
          </li>
        ))}
      </ol>
    </div>
  );
}
