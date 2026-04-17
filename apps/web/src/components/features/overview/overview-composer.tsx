"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface OverviewComposerAction {
  id: string;
  label: string;
  icon?: LucideIcon;
  onSelect?: () => void;
}

interface OverviewComposerProps {
  placeholder: string;
  submitLabel: string;
  onSubmit?: (value: string) => void;
  actions?: OverviewComposerAction[];
  className?: string;
}

export function OverviewComposer({
  placeholder,
  submitLabel,
  onSubmit,
  actions,
  className,
}: OverviewComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    const max = 160;
    const next = Math.min(node.scrollHeight, max);
    node.style.height = `${next}px`;
  }, []);

  useLayoutEffect(() => {
    resize();
  }, [resize, value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit?.(trimmed);
    setValue("");
  }, [onSubmit, value]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const disabled = !value.trim();

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div
        className={cn(
          "flex items-end gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2 transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "focus-within:border-[var(--border-strong)] focus-within:bg-[var(--panel)]",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="block min-h-[32px] w-full resize-none bg-transparent px-1 py-1 text-[var(--font-size-md)] leading-[1.4] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
          aria-label={placeholder}
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled}
          aria-label={submitLabel}
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-transparent transition-[background-color,border-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
            disabled
              ? "bg-[var(--surface-hover)] text-[var(--text-quaternary)]"
              : "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:scale-[0.96]",
          )}
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>

      {actions && actions.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.id}
                type="button"
                onClick={action.onSelect}
                className={cn(
                  "inline-flex h-8 items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-transparent px-3 text-[0.8125rem] font-medium text-[var(--text-secondary)]",
                  "transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
                )}
              >
                {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
                <span>{action.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
