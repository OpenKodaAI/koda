"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  buildCommands,
  groupCommands,
  rankCommands,
  type Command,
  type CommandBarContext,
} from "./command-registry";

export interface CommandBarProps {
  ctx: CommandBarContext;
  mode?: "inline" | "modal";
  placeholder: string;
  emptyState: string;
  shortcutHint?: string;
  autoFocus?: boolean;
  className?: string;
  onAfterExecute?: () => void;
  pillsSlot?: ReactNode;
}

export function CommandBar({
  ctx,
  mode = "inline",
  placeholder,
  emptyState,
  shortcutHint,
  autoFocus = false,
  className,
  onAfterExecute,
  pillsSlot,
}: CommandBarProps) {
  const listId = useId();
  const [value, setValue] = useState("");
  const [activeIndexRaw, setActiveIndex] = useState(0);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const commands = useMemo(() => buildCommands(ctx), [ctx]);
  const ranked = useMemo(() => rankCommands(commands, value), [commands, value]);
  const groups = useMemo(() => groupCommands(ranked, ctx.t), [ranked, ctx.t]);

  useEffect(() => {
    if (!autoFocus) return;
    // Autofocus without asking the browser to scroll the page. Native
    // `autoFocus` on an input inside a Radix Dialog can trigger
    // scrollIntoView on mount, which visually drags the page content upward
    // when the modal appears over the home screen.
    const raf = window.requestAnimationFrame(() => {
      inputRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(raf);
  }, [autoFocus]);

  const flat = useMemo(() => groups.flatMap((group) => group.commands), [groups]);
  const activeIndex = flat.length === 0 ? 0 : Math.min(activeIndexRaw, flat.length - 1);

  const execute = useCallback(
    (command: Command) => {
      command.onExecute();
      setValue("");
      setActiveIndex(0);
      onAfterExecute?.();
    },
    [onAfterExecute],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (flat.length === 0 && event.key !== "Escape") return;

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => (index + 1) % Math.max(1, flat.length));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => (index - 1 + flat.length) % Math.max(1, flat.length));
        return;
      }
      if (event.key === "Enter") {
        const command = flat[activeIndex];
        if (command) {
          event.preventDefault();
          execute(command);
        }
        return;
      }
      if (event.key === "Escape") {
        if (value) {
          event.preventDefault();
          setValue("");
          return;
        }
        if (mode === "inline") {
          inputRef.current?.blur();
        }
      }
    },
    [activeIndex, execute, flat, mode, value],
  );

  const open = mode === "modal" || isFocused || value.length > 0;
  const isInline = mode === "inline";

  const activeCommandId = flat[activeIndex]?.id;

  const resolveIndex = useCallback(
    (commandId: string) => flat.findIndex((command) => command.id === commandId),
    [flat],
  );

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative flex flex-col",
        isInline ? "gap-4" : "gap-0",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 px-3 transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          isInline
            ? cn(
                "rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] py-2",
                isFocused && "border-[var(--border-strong)] bg-[var(--panel)]",
              )
            : "bg-transparent py-3",
        )}
        onPointerDown={(event) => {
          if (event.target !== inputRef.current) {
            event.preventDefault();
            inputRef.current?.focus();
          }
        }}
      >
        <Search className="h-4 w-4 shrink-0 text-[var(--text-quaternary)]" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open && flat.length > 0}
          aria-controls={listId}
          aria-activedescendant={activeCommandId ? `${listId}-${activeCommandId}` : undefined}
          aria-autocomplete="list"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={(event) => {
            if (
              event.relatedTarget instanceof Node &&
              containerRef.current?.contains(event.relatedTarget)
            ) {
              return;
            }
            setIsFocused(false);
          }}
          placeholder={placeholder}
          className="block h-7 w-full min-w-0 bg-transparent text-[var(--font-size-md)] leading-[1.4] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
          aria-label={placeholder}
        />
        {shortcutHint && isInline ? (
          <span
            className="eyebrow hidden shrink-0 rounded-[var(--radius-chip)] border border-[var(--border-subtle)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-tertiary)] sm:inline-flex"
            aria-hidden="true"
          >
            {shortcutHint}
          </span>
        ) : null}
      </div>

      {pillsSlot ? <div className="flex justify-center">{pillsSlot}</div> : null}

      {open ? (
        <div
          className={cn(
            isInline
              ? "app-floating-panel !absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden !rounded-[var(--radius-input)]"
              : "flex min-h-0 flex-1 flex-col",
          )}
          role="listbox"
          id={listId}
        >
          {flat.length === 0 ? (
            <div className="px-4 py-6 text-center text-[12px] text-[var(--text-tertiary)]">
              {emptyState}
            </div>
          ) : (
            <div
              className={cn(
                "flex flex-col",
                isInline ? "max-h-[60vh] overflow-y-auto" : "flex-1 overflow-y-auto",
              )}
            >
              {groups.map((group) => (
                <div key={group.category} className="flex flex-col">
                  <div className="eyebrow px-4 pt-3 pb-1 text-[10px] text-[var(--text-quaternary)]">
                    {group.heading}
                  </div>
                  <ul className="flex flex-col">
                    {group.commands.map((command) => {
                      const index = resolveIndex(command.id);
                      const active = index === activeIndex;
                      const Icon = command.icon;
                      return (
                        <li key={command.id}>
                          <button
                            type="button"
                            id={`${listId}-${command.id}`}
                            role="option"
                            aria-selected={active}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseDown={(event) => {
                              event.preventDefault();
                              execute(command);
                            }}
                            className={cn(
                              "flex w-full items-center gap-3 px-4 py-2 text-left text-[13px] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                              active
                                ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                            )}
                          >
                            <Icon className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
                            <span className="flex-1 truncate">{command.label}</span>
                            {command.description ? (
                              <span className="shrink-0 truncate text-[12px] text-[var(--text-quaternary)]">
                                {command.description}
                              </span>
                            ) : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
