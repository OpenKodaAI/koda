"use client";

import { forwardRef, type KeyboardEvent, type SyntheticEvent } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export interface ComposerTextareaProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: () => void;
  disabled: boolean;
  busy: boolean;
  canSubmit: boolean;
  placeholder: string;
  /** Active option id for ARIA combobox + listbox pairing. */
  activeDescendantId?: string;
  /** Called whenever the textarea selection / caret changes. */
  onSelect?: (event: SyntheticEvent<HTMLTextAreaElement>) => void;
}

export const ComposerTextarea = forwardRef<HTMLTextAreaElement, ComposerTextareaProps>(
  function ComposerTextarea(
    {
      value,
      onChange,
      onKeyDown,
      onSubmit,
      disabled,
      busy,
      canSubmit,
      placeholder,
      activeDescendantId,
      onSelect,
    },
    ref,
  ) {
    const { t } = useAppI18n();

    return (
      <div className="flex items-end gap-2 px-3 pt-3">
        <textarea
          ref={ref}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onClick={onSelect}
          aria-activedescendant={activeDescendantId}
          disabled={disabled}
          rows={1}
          placeholder={placeholder}
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
          onClick={(event) => {
            event.preventDefault();
            if (canSubmit) onSubmit();
          }}
          aria-label={t("chat.composer.send", { defaultValue: "Send" })}
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
            "transition-[background-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
            canSubmit
              ? "bg-[var(--accent)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)] active:scale-[0.96]"
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
    );
  },
);
