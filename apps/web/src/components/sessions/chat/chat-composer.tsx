"use client";

import { useCallback, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, ChevronDown, Loader2 } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAutoGrowTextarea } from "@/hooks/use-auto-grow-textarea";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  agentId?: string | null;
  onAgentChange?: (agentId: string | undefined) => void;
  lockedAgent?: boolean;
  modelLabel?: string | null;
  disabled?: boolean;
  busy?: boolean;
  placeholder?: string;
  helper?: string | null;
  error?: string | null;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  agentId,
  onAgentChange,
  lockedAgent = false,
  modelLabel,
  disabled = false,
  busy = false,
  placeholder,
  helper,
  error,
}: ChatComposerProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const textareaRef = useAutoGrowTextarea(value);
  const canSubmit = Boolean(value.trim()) && !disabled && !busy;

  const handleSubmit = useCallback(
    (event?: FormEvent) => {
      event?.preventDefault();
      if (!canSubmit) return;
      onSubmit();
    },
    [canSubmit, onSubmit],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Enter") return;
      if (event.shiftKey) return;
      const submitModifier = event.metaKey || event.ctrlKey;
      if (!submitModifier) return;
      event.preventDefault();
      handleSubmit();
    },
    [handleSubmit],
  );

  const activeAgent = agents.find((agent) => agent.id === agentId);
  const agentLabel = activeAgent?.label ?? agentId ?? null;

  const resolvedPlaceholder =
    placeholder ?? t("chat.composer.placeholder", { defaultValue: "Send a message…" });

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-auto w-full max-w-[720px] px-6 pb-6 pt-2"
      aria-label={t("chat.composer.placeholder", { defaultValue: "Send a message…" })}
    >
      <div
        className={cn(
          "flex flex-col rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] shadow-[var(--shadow-xs)]",
          "transition-[border-color,background-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "focus-within:border-[var(--accent)] focus-within:bg-[var(--panel)] focus-within:shadow-[0_0_0_1px_var(--accent-muted)]",
          disabled && "opacity-70",
        )}
      >
        <div className="flex items-end gap-2 px-3 pt-3">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            placeholder={resolvedPlaceholder}
            autoComplete="off"
            spellCheck
            className={cn(
              "min-h-[24px] max-h-[160px] flex-1 resize-none bg-transparent py-1 text-[var(--font-size-md)] leading-[1.5]",
              "text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] outline-none",
            )}
          />
          <button
            type="submit"
            disabled={!canSubmit}
            aria-label={t("chat.composer.send", { defaultValue: "Send" })}
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
              "transition-[background-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
              canSubmit
                ? "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:scale-[0.96]"
                : "bg-[var(--panel-strong)] text-[var(--text-quaternary)]",
            )}
          >
            {busy ? (
              <Loader2 className="icon-sm animate-spin" strokeWidth={1.75} />
            ) : (
              <ArrowUp className="icon-sm" strokeWidth={2} />
            )}
          </button>
        </div>

        <div className="flex items-center justify-between gap-3 px-3 pb-2 pt-1">
          <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {t("chat.composer.sendHint", { defaultValue: "⌘↵ to send" })}
          </span>
          <div className="flex items-center gap-1.5 text-[0.6875rem] text-[var(--text-tertiary)]">
            {modelLabel ? (
              <span className="font-mono tracking-[-0.01em]">{modelLabel}</span>
            ) : null}
            {modelLabel && agentLabel ? (
              <span className="text-[var(--text-quaternary)]">·</span>
            ) : null}
            {agentLabel ? (
              lockedAgent ? (
                <span className="truncate max-w-[160px]">{agentLabel}</span>
              ) : (
                <Popover>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 truncate max-w-[160px] rounded-[var(--radius-chip)] px-1.5 py-0.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                    >
                      <span className="truncate">{agentLabel}</span>
                      <ChevronDown
                        className="icon-xs shrink-0 opacity-60"
                        strokeWidth={1.75}
                        aria-hidden
                      />
                    </button>
                  </PopoverTrigger>
                  <PopoverContent align="end" sideOffset={8} className="w-60 p-1">
                    <ul role="listbox" className="flex flex-col">
                      {agents.map((agent) => {
                        const active = agent.id === agentId;
                        return (
                          <li key={agent.id}>
                            <button
                              type="button"
                              role="option"
                              aria-selected={active}
                              onClick={() => onAgentChange?.(agent.id)}
                              className={cn(
                                "flex w-full items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-left text-[0.8125rem]",
                                "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                                active
                                  ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                                  : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                              )}
                            >
                              <span
                                aria-hidden
                                className="h-1.5 w-1.5 shrink-0 rounded-full"
                                style={{ background: agent.color ?? "#7A8799" }}
                              />
                              <span className="truncate">{agent.label || agent.id}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </PopoverContent>
                </Popover>
              )
            ) : null}
          </div>
        </div>
      </div>

      {error ? (
        <p className="mt-2 px-1 text-[0.75rem] text-[var(--tone-danger-dot)]">{error}</p>
      ) : helper ? (
        <p className="mt-2 px-1 text-[0.75rem] text-[var(--text-tertiary)]">{helper}</p>
      ) : null}
    </form>
  );
}
