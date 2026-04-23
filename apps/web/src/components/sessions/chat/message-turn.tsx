"use client";

import { type ReactNode } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn, formatRelativeTime } from "@/lib/utils";

interface MessageTurnProps {
  role: "user" | "assistant";
  timestamp?: string | null;
  children: ReactNode;
  failed?: boolean;
  onRetry?: () => void;
}

export function MessageTurn({
  role,
  timestamp,
  children,
  failed = false,
  onRetry,
}: MessageTurnProps) {
  const { t } = useAppI18n();

  if (role === "user") {
    const showMeta = Boolean(timestamp || failed);
    return (
      <div className="group flex flex-col gap-1.5 animate-in fade-in-0 duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]">
        <div className="flex w-full justify-end">{children}</div>
        {showMeta ? (
          <div className="flex items-center justify-end gap-2 pr-1 text-[0.6875rem] text-[var(--text-quaternary)]">
            {timestamp ? (
              <span
                className={cn(
                  "opacity-0 transition-opacity duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                  "group-hover:opacity-100 focus-within:opacity-100",
                )}
              >
                {formatRelativeTime(timestamp)}
              </span>
            ) : null}
            {failed ? (
              <>
                <span className="text-[var(--tone-danger-dot)]">
                  {t("chat.thread.failed", { defaultValue: "Failed to send" })}
                </span>
                {onRetry ? (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="rounded-[var(--radius-panel-sm)] px-1.5 py-0.5 text-[var(--accent)] transition-colors hover:bg-[var(--hover-tint)]"
                  >
                    {t("chat.thread.retry", { defaultValue: "Retry" })}
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="group flex flex-col gap-2 animate-in fade-in-0 duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]">
      {children}
      {timestamp ? (
        <div className="flex items-center gap-2 text-[0.6875rem] text-[var(--text-quaternary)]">
          <span
            className={cn(
              "opacity-0 transition-opacity duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "group-hover:opacity-100 focus-within:opacity-100",
            )}
          >
            {formatRelativeTime(timestamp)}
          </span>
        </div>
      ) : null}
    </div>
  );
}
