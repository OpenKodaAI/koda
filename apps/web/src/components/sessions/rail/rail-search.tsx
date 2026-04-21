"use client";

import { Search, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface RailSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function RailSearch({ value, onChange, placeholder, className }: RailSearchProps) {
  const { t } = useAppI18n();
  const resolvedPlaceholder =
    placeholder ?? t("chat.rail.search", { defaultValue: "Search conversations" });

  return (
    <label
      className={cn(
        "flex h-9 w-full items-center gap-2 rounded-[var(--radius-input)] bg-[var(--panel-soft)] px-3",
        "transition-[background-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-within:bg-[var(--panel)] focus-within:shadow-[0_0_0_1px_var(--accent-muted)]",
        className,
      )}
    >
      <Search className="icon-sm text-[var(--text-quaternary)]" strokeWidth={1.75} aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={resolvedPlaceholder}
        className="flex-1 bg-transparent text-[var(--font-size-sm)] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("chat.rail.clearSearch", { defaultValue: "Clear search" })}
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]"
        >
          <X className="icon-xs" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </label>
  );
}
