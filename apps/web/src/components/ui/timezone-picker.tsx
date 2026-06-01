"use client";

import * as React from "react";
import { Check, ChevronDown, Globe2, Search } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/**
 * Searchable IANA-timezone picker built on the canonical Popover + Input
 * primitives. Trigger styling mirrors SelectTrigger (same height, padding,
 * border, focus ring) so it slots into existing forms without visual drift.
 *
 * Source list: `Intl.supportedValuesOf("timeZone")` — every IANA zone the
 * runtime knows about. The function is widely available (Node 18+, Safari
 * 15.4+, Chrome 99+, FF 93+) but we ship a sensible curated fallback so SSR
 * and older runtimes still get a working picker.
 */
export interface TimezonePickerProps {
  value: string;
  onValueChange: (next: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  placeholder?: string;
  className?: string;
  title?: string;
  searchPlaceholder?: string;
  emptyLabel?: string;
}

const FALLBACK_ZONES = [
  "UTC",
  "America/Sao_Paulo",
  "America/New_York",
  "America/Los_Angeles",
  "America/Chicago",
  "America/Denver",
  "America/Mexico_City",
  "America/Buenos_Aires",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Madrid",
  "Europe/Lisbon",
  "Africa/Johannesburg",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Asia/Singapore",
  "Asia/Kolkata",
  "Australia/Sydney",
];

function listSupportedTimeZones(): readonly string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  if (typeof intl.supportedValuesOf === "function") {
    try {
      const zones = intl.supportedValuesOf("timeZone");
      if (Array.isArray(zones) && zones.length > 0) {
        return zones;
      }
    } catch {
      // fall through to curated list
    }
  }
  return FALLBACK_ZONES;
}

const ZONE_LIST: readonly string[] = listSupportedTimeZones();

function offsetLabel(zone: string): string {
  try {
    const formatter = new Intl.DateTimeFormat("en", {
      timeZone: zone,
      timeZoneName: "shortOffset",
    });
    const parts = formatter.formatToParts(new Date());
    const offset = parts.find((part) => part.type === "timeZoneName")?.value ?? "";
    if (!offset) return "";
    // shortOffset typically yields "GMT-3" / "GMT+05:30"; normalize bare "GMT" to "UTC".
    return offset === "GMT" ? "UTC" : offset.replace(/^GMT/, "UTC");
  } catch {
    return "";
  }
}

function normalize(text: string): string {
  return text.toLowerCase().replace(/[_/\s-]+/g, " ").trim();
}

export const TimezonePicker = React.forwardRef<HTMLButtonElement, TimezonePickerProps>(
  function TimezonePicker(
    {
      value,
      onValueChange,
      disabled,
      invalid,
      placeholder = "Selecionar fuso horário…",
      className,
      title,
      searchPlaceholder = "Buscar fuso horário",
      emptyLabel = "Nenhum fuso encontrado",
    },
    ref,
  ) {
    const [open, setOpen] = React.useState(false);
    const [query, setQuery] = React.useState("");
    const inputRef = React.useRef<HTMLInputElement | null>(null);
    const listRef = React.useRef<HTMLDivElement | null>(null);
    const [activeIndex, setActiveIndex] = React.useState(0);

    const filtered = React.useMemo(() => {
      const q = normalize(query);
      if (!q) return ZONE_LIST;
      return ZONE_LIST.filter((zone) => normalize(zone).includes(q));
    }, [query]);

    React.useEffect(() => {
      setActiveIndex(0);
    }, [query, open]);

    React.useEffect(() => {
      if (open) {
        // Defer focus to next tick so Popover content is mounted.
        const id = window.setTimeout(() => inputRef.current?.focus(), 0);
        return () => window.clearTimeout(id);
      }
      setQuery("");
    }, [open]);

    function commit(next: string) {
      onValueChange(next);
      setOpen(false);
    }

    function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((idx) => Math.min(idx + 1, Math.max(filtered.length - 1, 0)));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((idx) => Math.max(idx - 1, 0));
      } else if (event.key === "Enter") {
        const selection = filtered[activeIndex];
        if (selection) {
          event.preventDefault();
          commit(selection);
        }
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    }

    React.useEffect(() => {
      if (!open) return;
      const list = listRef.current;
      if (!list) return;
      const target = list.querySelector<HTMLElement>(`[data-tz-index="${activeIndex}"]`);
      target?.scrollIntoView({ block: "nearest" });
    }, [activeIndex, open]);

    const offset = value ? offsetLabel(value) : "";

    return (
      <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
        <PopoverTrigger asChild>
          <button
            ref={ref}
            type="button"
            disabled={disabled}
            data-invalid={invalid || undefined}
            aria-haspopup="listbox"
            title={title}
            className={cn(
              "flex h-9 w-full items-center justify-between gap-2 rounded-[var(--radius-input)] border bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-primary)] outline-none",
              "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "border-[var(--border-subtle)] hover:border-[var(--border-strong)]",
              "focus-visible:border-[var(--accent)] data-[state=open]:border-[var(--accent)]",
              invalid && "border-[var(--tone-danger-border)] focus-visible:border-[var(--tone-danger-border)]",
              disabled && "cursor-not-allowed opacity-60",
              className,
            )}
          >
            <span className="flex min-w-0 items-center gap-2">
              <Globe2 className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
              {value ? (
                <span className="truncate">{value}</span>
              ) : (
                <span className="truncate text-[var(--text-quaternary)]">{placeholder}</span>
              )}
            </span>
            <span className="flex shrink-0 items-center gap-2 text-[var(--text-tertiary)]">
              {offset ? (
                <span className="font-mono text-[0.6875rem] tabular-nums">{offset}</span>
              ) : null}
              <ChevronDown className="icon-sm" strokeWidth={1.75} />
            </span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="w-[var(--radix-popover-trigger-width)] min-w-[18rem] p-0"
        >
          <div className="flex items-center gap-2 border-b border-[var(--divider-hair)] px-3">
            <Search className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={searchPlaceholder}
              className="h-9 w-full bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
            />
          </div>
          <div ref={listRef} role="listbox" className="max-h-[18rem] overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-3 text-center text-[0.75rem] text-[var(--text-tertiary)]">
                {emptyLabel}
              </div>
            ) : (
              filtered.map((zone, index) => {
                const selected = zone === value;
                const active = index === activeIndex;
                const zoneOffset = offsetLabel(zone);
                return (
                  <button
                    key={zone}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    data-tz-index={index}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => commit(zone)}
                    className={cn(
                      "flex w-full items-center justify-between gap-3 rounded-[var(--radius-chip)] px-2.5 py-1.5 text-left text-[0.8125rem] text-[var(--text-primary)]",
                      "transition-[background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                      active && "bg-[var(--hover-tint)]",
                      selected && "bg-[var(--panel-strong)]",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {selected ? (
                        <Check className="icon-sm shrink-0 text-[var(--accent)]" strokeWidth={1.75} />
                      ) : (
                        <span className="inline-block w-[14px] shrink-0" aria-hidden />
                      )}
                      <span className="truncate">{zone}</span>
                    </span>
                    {zoneOffset ? (
                      <span className="shrink-0 font-mono text-[0.6875rem] tabular-nums text-[var(--text-tertiary)]">
                        {zoneOffset}
                      </span>
                    ) : null}
                  </button>
                );
              })
            )}
          </div>
        </PopoverContent>
      </Popover>
    );
  },
);
