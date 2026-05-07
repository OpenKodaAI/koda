"use client";

import {
  SELECT_ALL_VALUE,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
      <Select
        value={selectedType === "" ? SELECT_ALL_VALUE : selectedType}
        onValueChange={(v) => onTypeChange(v === SELECT_ALL_VALUE ? "" : v)}
      >
        <SelectTrigger id="event-type-filter" className="min-w-[220px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SELECT_ALL_VALUE}>{tl("Todos os eventos")}</SelectItem>
          {eventTypes.map((type) => (
            <SelectItem key={type} value={type}>
              {type}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
