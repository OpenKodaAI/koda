"use client";

import { useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface DatePickerProps {
  value: Date;
  onChange: (next: Date) => void;
  disabled?: boolean;
  className?: string;
}

export function DatePicker({ value, onChange, disabled = false, className }: DatePickerProps) {
  const { i18n, tl } = useAppI18n();
  const locale = i18n.language || "en-US";
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => startOfMonth(value));

  const today = useMemo(() => new Date(), []);

  const days = useMemo(() => {
    return eachDayOfInterval({
      start: startOfWeek(month, { weekStartsOn: 0 }),
      end: endOfWeek(endOfMonth(month), { weekStartsOn: 0 }),
    });
  }, [month]);

  const dayLabels = useMemo(() => {
    const formatter = new Intl.DateTimeFormat(locale, { weekday: "short" });
    const baseSunday = new Date(2024, 0, 7);
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(baseSunday);
      date.setDate(baseSunday.getDate() + i);
      return formatter.format(date).slice(0, 3);
    });
  }, [locale]);

  const monthLabel = useMemo(() => {
    return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(month);
  }, [month, locale]);

  const triggerLabel = useMemo(() => {
    return new Intl.DateTimeFormat(locale, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(value);
  }, [value, locale]);

  function handlePick(date: Date) {
    const next = new Date(date);
    next.setHours(value.getHours(), value.getMinutes(), 0, 0);
    onChange(next);
    setOpen(false);
  }

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
            <CalendarDays className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
            <span className="truncate">{triggerLabel}</span>
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[18rem] p-3">
        <header className="mb-2 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => setMonth((current) => subMonths(current, 1))}
            className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
            aria-label={tl("Previous month")}
          >
            <ChevronLeft className="icon-sm" strokeWidth={1.75} />
          </button>
          <span className="text-[0.8125rem] font-medium capitalize text-[var(--text-primary)]">
            {monthLabel}
          </span>
          <button
            type="button"
            onClick={() => setMonth((current) => addMonths(current, 1))}
            className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
            aria-label={tl("Next month")}
          >
            <ChevronRight className="icon-sm" strokeWidth={1.75} />
          </button>
        </header>
        <div className="grid grid-cols-7 gap-1">
          {dayLabels.map((label, index) => (
            <span
              key={`${label}-${index}`}
              className="flex h-6 items-center justify-center font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]"
            >
              {label}
            </span>
          ))}
          {days.map((day) => {
            const sameMonth = isSameMonth(day, month);
            const isSelected = isSameDay(day, value);
            const isToday = isSameDay(day, today);
            return (
              <button
                key={day.toISOString()}
                type="button"
                onClick={() => handlePick(day)}
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-[var(--radius-panel-sm)] text-[0.8125rem]",
                  "transition-[background-color,color,border-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                  isSelected
                    ? "bg-[var(--accent)] text-white"
                    : sameMonth
                      ? "text-[var(--text-primary)] hover:bg-[var(--hover-tint)]"
                      : "text-[var(--text-quaternary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-tertiary)]",
                  !isSelected && isToday && "ring-1 ring-[var(--border-strong)]",
                )}
              >
                {day.getDate()}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
