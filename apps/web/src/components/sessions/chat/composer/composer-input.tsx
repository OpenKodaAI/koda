"use client";

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  type KeyboardEvent,
  type SyntheticEvent,
} from "react";
import { ArrowUp, LoaderCircle } from "lucide-react";
import { useAutoGrowTextarea } from "@/hooks/use-auto-grow-textarea";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export interface ComposerInputHandle {
  focus(): void;
  setSelectionRange(start: number, end?: number): void;
  readonly value: string;
  readonly selectionStart: number;
  readonly domNode: HTMLTextAreaElement | null;
}

interface ComposerInputProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSubmit: () => void;
  disabled: boolean;
  busy: boolean;
  canSubmit: boolean;
  placeholder: string;
  activeDescendantId?: string;
  onSelect?: (event: SyntheticEvent<HTMLTextAreaElement>) => void;
}

const MIN_HEIGHT = 56;
const MAX_HEIGHT = 200;

export const ComposerInput = forwardRef<ComposerInputHandle, ComposerInputProps>(
  function ComposerInput(
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
    const localRef = useRef<HTMLTextAreaElement | null>(null);
    const autoGrowRef = useAutoGrowTextarea(value, {
      minHeight: MIN_HEIGHT,
      maxHeight: MAX_HEIGHT,
    });

    const setRefs = useCallback((node: HTMLTextAreaElement | null) => {
      localRef.current = node;
      autoGrowRef.current = node;
    }, [autoGrowRef]);

    useImperativeHandle(
      ref,
      () => ({
        focus: () => localRef.current?.focus(),
        setSelectionRange: (start, end) => {
          const node = localRef.current;
          if (!node) return;
          node.setSelectionRange(start, end ?? start);
        },
        get value() {
          return localRef.current?.value ?? "";
        },
        get selectionStart() {
          return localRef.current?.selectionStart ?? 0;
        },
        get domNode() {
          return localRef.current;
        },
      }),
      [],
    );

    return (
      <div className="flex items-start gap-2 px-3 pt-3">
        <textarea
          ref={setRefs}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onClick={onSelect}
          aria-activedescendant={activeDescendantId}
          aria-label={placeholder}
          disabled={disabled}
          rows={1}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck
          className={cn(
            "min-h-[56px] max-h-[200px] flex-1 resize-none bg-transparent py-1 text-[var(--font-size-md)] leading-[1.5]",
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
            <LoaderCircle className="icon-sm animate-spin" strokeWidth={1.75} />
          ) : (
            <ArrowUp className="icon-sm" strokeWidth={2} />
          )}
        </button>
      </div>
    );
  },
);
