"use client";

import { SessionRichText } from "@/components/sessions/session-rich-text";
import { cn } from "@/lib/utils";

interface UserMessageProps {
  text: string;
  pending?: boolean;
  failed?: boolean;
}

export function UserMessage({ text, pending = false, failed = false }: UserMessageProps) {
  return (
    <div
      className={cn(
        "max-w-[75%] rounded-[var(--radius-panel-sm)] px-4 py-3",
        "text-[length:var(--font-size-md)] leading-[1.55] text-[color:var(--text-primary)]",
        failed ? "bg-[var(--tone-danger-bg)]" : "bg-[var(--panel-soft)]",
        pending && "opacity-70 has-[:focus-visible]:opacity-100",
      )}
    >
      <SessionRichText content={text} variant="user" />
    </div>
  );
}
