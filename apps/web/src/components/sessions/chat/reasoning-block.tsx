"use client";

import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface ReasoningBlockProps {
  children: ReactNode;
  streaming?: boolean;
  durationLabel?: string | null;
  defaultOpen?: boolean;
}

export function ReasoningBlock({
  children,
  streaming = false,
  durationLabel,
  defaultOpen = false,
}: ReasoningBlockProps) {
  const { t } = useAppI18n();
  const [open, setOpen] = useState(defaultOpen);

  const header = streaming
    ? t("chat.reasoning.expandLabelStreaming", { defaultValue: "Thinking…" })
    : durationLabel
      ? t("chat.reasoning.expandLabelDone", {
          defaultValue: "Thought for {{duration}}",
          duration: durationLabel,
        })
      : t("chat.reasoning.expandLabelDoneNoDuration", { defaultValue: "Reasoning" });

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={cn(
          "inline-flex w-fit items-center gap-1.5 rounded-[var(--radius-chip)] px-1.5 py-0.5 text-[0.75rem]",
          "text-[var(--text-tertiary)] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]",
        )}
      >
        <ChevronRight
          className={cn(
            "icon-xs transition-transform duration-[200ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            open && "rotate-90",
          )}
          strokeWidth={1.75}
          aria-hidden
        />
        <span className={cn(streaming && "chat-reasoning--streaming")}>{header}</span>
      </button>
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-[280ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div
            className={cn(
              "pl-4 py-1",
              "italic text-[0.875rem] leading-[1.55] text-[var(--text-tertiary)]",
              "max-h-[320px] overflow-y-auto",
            )}
          >
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
