"use client";

import { LoaderCircle, Search, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface RailSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  loading?: boolean;
  className?: string;
}

export function RailSearch({ value, onChange, placeholder, loading = false, className }: RailSearchProps) {
  const { t } = useAppI18n();
  const resolvedPlaceholder =
    placeholder ?? t("chat.rail.search", undefined);

  return (
    <label
      className={cn(
        "flex h-9 w-full items-center gap-2 rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3",
        "transition-[background-color,border-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-within:border-[color:var(--focus-ring)] focus-within:bg-[var(--panel)] focus-within:outline focus-within:outline-[color:var(--focus-ring)]",
        className,
      )}
    >
      {loading ? (
        <span
          role="status"
          aria-label={t("chat.rail.searching", undefined)}
        >
          <LoaderCircle
            className="icon-sm animate-spin text-[color:var(--text-quaternary)]"
            strokeWidth={1.75}
            aria-hidden
          />
        </span>
      ) : (
        <Search className="icon-sm text-[color:var(--text-quaternary)]" strokeWidth={1.75} aria-hidden />
      )}
      <input
        type="text"
        role="searchbox"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={resolvedPlaceholder}
        className="search-input--custom-clear flex-1 bg-transparent text-[length:var(--font-size-sm)] text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-quaternary)]"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("chat.rail.clearSearch", undefined)}
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[color:var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[color:var(--text-secondary)]"
        >
          <X className="icon-xs" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </label>
  );
}
