"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface ThinkingIndicatorProps {
  label?: string;
  className?: string;
}

export function ThinkingIndicator({ label, className }: ThinkingIndicatorProps) {
  const { t } = useAppI18n();
  const resolvedLabel = label ?? t("chat.thread.thinking", { defaultValue: "Thinking…" });

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex h-6 items-center gap-2 text-[var(--text-tertiary)]",
        className,
      )}
    >
      <span className="chat-thinking-dots" aria-hidden>
        <span />
        <span />
        <span />
      </span>
      <span className="text-[0.75rem]">{resolvedLabel}</span>
    </div>
  );
}
