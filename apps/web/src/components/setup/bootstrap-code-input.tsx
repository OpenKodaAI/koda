"use client";

import {
  type ClipboardEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";

/**
 * Alphabet that matches koda/control_plane/operator_auth.py:_BOOTSTRAP_ALPHABET.
 * We exclude `I`, `O`, `0`, `1` deliberately to avoid visual ambiguity.
 */
const BOOTSTRAP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const GROUPS = [4, 4, 4] as const;
const TOTAL = GROUPS.reduce((sum, n) => sum + n, 0);

function parseIncoming(value: string): string[] {
  const filtered = Array.from(value.toUpperCase())
    .map((ch) => (BOOTSTRAP_ALPHABET.includes(ch) ? ch : ""))
    .filter(Boolean);
  return filtered.slice(0, TOTAL);
}

function formatWithDashes(chars: string[]): string {
  const segments: string[] = [];
  let cursor = 0;
  for (const size of GROUPS) {
    segments.push(chars.slice(cursor, cursor + size).join(""));
    cursor += size;
  }
  // Drop trailing empty segments so partial values don't render stray dashes.
  while (segments.length > 1 && segments[segments.length - 1] === "") {
    segments.pop();
  }
  return segments.join("-");
}

function splitValueIntoChars(value: string): string[] {
  const parsed = parseIncoming(value);
  return Array.from({ length: TOTAL }, (_, i) => parsed[i] ?? "");
}

export interface BootstrapCodeInputProps {
  id?: string;
  value: string;
  onChange: (next: string) => void;
  onComplete?: (final: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
  invalid?: boolean;
}

export function BootstrapCodeInput({
  id,
  value,
  onChange,
  onComplete,
  disabled,
  ariaLabel,
  invalid,
}: BootstrapCodeInputProps) {
  const chars = useMemo(() => splitValueIntoChars(value), [value]);
  const refs = useRef<Array<HTMLInputElement | null>>(Array.from({ length: TOTAL }, () => null));
  const reactId = useId();
  const groupId = id ?? reactId;
  // Only used to hint layout animations on the first input; the individual
  // boxes own their own focus state via :focus.
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const commit = useCallback(
    (nextChars: string[]) => {
      const formatted = formatWithDashes(nextChars);
      onChange(formatted);
      if (nextChars.every((c) => c !== "") && onComplete) {
        onComplete(formatted);
      }
    },
    [onChange, onComplete],
  );

  const focusIndex = useCallback((index: number) => {
    const clamped = Math.max(0, Math.min(TOTAL - 1, index));
    refs.current[clamped]?.focus();
    refs.current[clamped]?.select();
  }, []);

  const handleChangeAt = useCallback(
    (index: number, raw: string) => {
      // A single change event can carry multiple characters (paste into a
      // single box, mobile autofill). Distribute them across the remaining
      // slots instead of dropping everything but the first.
      const incoming = parseIncoming(raw);
      if (incoming.length === 0) {
        const next = [...chars];
        if (next[index] === "") return;
        next[index] = "";
        commit(next);
        return;
      }
      const next = [...chars];
      let cursor = index;
      for (const ch of incoming) {
        if (cursor >= TOTAL) break;
        next[cursor] = ch;
        cursor += 1;
      }
      commit(next);
      // Focus the next empty slot, or the last slot if the value is full.
      const nextEmpty = next.findIndex((c, i) => i >= cursor && c === "");
      const targetIndex = nextEmpty === -1 ? Math.min(TOTAL - 1, cursor) : nextEmpty;
      focusIndex(targetIndex);
    },
    [chars, commit, focusIndex],
  );

  const handleKeyDown = useCallback(
    (index: number, event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Backspace") {
        if (chars[index] !== "") {
          // Let the change event clear the slot.
          return;
        }
        event.preventDefault();
        if (index > 0) {
          const next = [...chars];
          next[index - 1] = "";
          commit(next);
          focusIndex(index - 1);
        }
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        focusIndex(index - 1);
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        focusIndex(index + 1);
        return;
      }
      if (event.key === "Home") {
        event.preventDefault();
        focusIndex(0);
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        focusIndex(TOTAL - 1);
        return;
      }
    },
    [chars, commit, focusIndex],
  );

  const handlePaste = useCallback(
    (index: number, event: ClipboardEvent<HTMLInputElement>) => {
      const clipboard = event.clipboardData?.getData("text") ?? "";
      if (!clipboard) return;
      event.preventDefault();
      handleChangeAt(index, clipboard);
    },
    [handleChangeAt],
  );

  // Auto-focus the first empty slot whenever the value changes externally
  // (e.g. controlled from a parent), but only when the user is not currently
  // typing in another slot.
  useEffect(() => {
    if (activeIndex !== null) return;
    if (disabled) return;
    // Don't auto-focus on mount — that steals focus from earlier form fields.
    // The hook only runs to scroll/select if the value changed externally.
  }, [activeIndex, disabled, value]);

  let globalIndex = 0;
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "bootstrap-code-input",
        disabled && "bootstrap-code-input--disabled",
        invalid && "bootstrap-code-input--invalid",
      )}
    >
      {GROUPS.map((size, groupIdx) => (
        <div key={`${groupId}-g${groupIdx}`} className="bootstrap-code-input__group">
          {Array.from({ length: size }, () => {
            const currentIndex = globalIndex++;
            return (
              <input
                key={`${groupId}-${currentIndex}`}
                ref={(el) => {
                  refs.current[currentIndex] = el;
                }}
                id={currentIndex === 0 ? groupId : undefined}
                type="text"
                inputMode="text"
                autoComplete={currentIndex === 0 ? "one-time-code" : "off"}
                autoCorrect="off"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={1}
                disabled={disabled}
                aria-label={
                  ariaLabel
                    ? `${ariaLabel} ${currentIndex + 1} / ${TOTAL}`
                    : `Character ${currentIndex + 1} of ${TOTAL}`
                }
                value={chars[currentIndex]}
                onFocus={() => {
                  setActiveIndex(currentIndex);
                  // Select the single character so typing replaces it.
                  window.requestAnimationFrame(() => {
                    refs.current[currentIndex]?.select();
                  });
                }}
                onBlur={() => setActiveIndex(null)}
                onChange={(event) => {
                  const raw = event.target.value;
                  // Strip the previously-existing character if the browser
                  // concatenated instead of replacing.
                  const effective =
                    raw.length > 1 && chars[currentIndex] && raw.startsWith(chars[currentIndex])
                      ? raw.slice(1)
                      : raw;
                  handleChangeAt(currentIndex, effective);
                }}
                onKeyDown={(event) => handleKeyDown(currentIndex, event)}
                onPaste={(event) => handlePaste(currentIndex, event)}
                className="bootstrap-code-input__cell"
              />
            );
          })}
          {groupIdx < GROUPS.length - 1 ? (
            <span aria-hidden="true" className="bootstrap-code-input__dash">
              –
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
