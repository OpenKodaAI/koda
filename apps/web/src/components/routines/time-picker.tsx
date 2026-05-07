"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Clock } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface TimePickerProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  className?: string;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function parseTime(value: string): { hour: number; minute: number } {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value || "");
  if (!match) return { hour: 9, minute: 0 };
  const hour = Math.min(23, Math.max(0, Number(match[1])));
  const minute = Math.min(59, Math.max(0, Number(match[2])));
  return { hour, minute };
}

export function TimePicker({ value, onChange, disabled = false, className }: TimePickerProps) {
  const [open, setOpen] = useState(false);
  const { hour, minute } = parseTime(value);
  const display = `${pad(hour)}:${pad(minute)}`;
  const hourListRef = useRef<HTMLDivElement | null>(null);
  const minuteListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const id = window.requestAnimationFrame(() => {
      hourListRef.current
        ?.querySelector<HTMLButtonElement>(`[data-h="${hour}"]`)
        ?.scrollIntoView({ block: "center" });
      minuteListRef.current
        ?.querySelector<HTMLButtonElement>(`[data-m="${minute - (minute % 5)}"]`)
        ?.scrollIntoView({ block: "center" });
    });
    return () => window.cancelAnimationFrame(id);
  }, [open, hour, minute]);

  return (
    <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "flex h-9 w-full items-center justify-between gap-2 rounded-[var(--radius-input)] border bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-primary)] outline-none",
            "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "border-[var(--border-subtle)] hover:border-[var(--border-strong)]",
            "focus-visible:border-[var(--accent)] data-[state=open]:border-[var(--accent)]",
            "disabled:cursor-not-allowed disabled:opacity-60",
            className,
          )}
        >
          <span className="flex min-w-0 items-center gap-2">
            <Clock className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
            <span className="font-mono text-[0.875rem]">{display}</span>
          </span>
          <ChevronDown className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[14rem] p-0">
        <div className="grid grid-cols-2 divide-x divide-[var(--divider-hair)]">
          <div ref={hourListRef} className="max-h-[15rem] overflow-y-auto py-1">
            {HOURS.map((h) => {
              const selected = h === hour;
              return (
                <button
                  key={h}
                  type="button"
                  data-h={h}
                  onClick={() => onChange(`${pad(h)}:${pad(minute)}`)}
                  className={cn(
                    "flex w-full items-center justify-center px-3 py-1.5 text-center font-mono text-[0.8125rem]",
                    "transition-[background-color,color] duration-[120ms]",
                    selected
                      ? "bg-[var(--panel-strong)] text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {pad(h)}
                </button>
              );
            })}
          </div>
          <div ref={minuteListRef} className="max-h-[15rem] overflow-y-auto py-1">
            {MINUTES.map((m) => {
              const selected = m === minute - (minute % 5);
              return (
                <button
                  key={m}
                  type="button"
                  data-m={m}
                  onClick={() => onChange(`${pad(hour)}:${pad(m)}`)}
                  className={cn(
                    "flex w-full items-center justify-center px-3 py-1.5 text-center font-mono text-[0.8125rem]",
                    "transition-[background-color,color] duration-[120ms]",
                    selected
                      ? "bg-[var(--panel-strong)] text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {pad(m)}
                </button>
              );
            })}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
