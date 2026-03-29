"use client";

import { ChevronDown } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface AuditFiltersProps {
  eventTypes: string[];
  selectedType: string;
  onTypeChange: (type: string) => void;
}

export function AuditFilters({ eventTypes, selectedType, onTypeChange }: AuditFiltersProps) {
  const { tl } = useAppI18n();

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
      <label
        htmlFor="event-type-filter"
        className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]"
      >
        {tl("Evento")}
      </label>
      <div className="relative min-w-[220px]">
        <select
          id="event-type-filter"
          value={selectedType}
          onChange={(e) => onTypeChange(e.target.value)}
          className="glass-card-sm min-w-[220px] appearance-none border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)] px-4 py-3 pr-11 text-sm text-[var(--text-primary)] outline-none transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] focus:border-[var(--border-strong)] focus:bg-[var(--surface-hover)]"
        >
          <option value="">{tl("Todos os eventos")}</option>
          {eventTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]" />
      </div>
    </div>
  );
}
