"use client";

import { useMemo, useState } from "react";
import { Plug2, Plus, Search, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { listAvailableConnectors } from "@/lib/routines/connectors";
import { cn } from "@/lib/utils";

interface ConnectorPickerProps {
  agentId: string | null;
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

export function ConnectorPicker({ agentId, value, onChange, disabled = false }: ConnectorPickerProps) {
  const { t } = useAppI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const allConnectors = useMemo(() => listAvailableConnectors(agentId), [agentId]);

  const selectedSet = useMemo(() => new Set(value), [value]);

  const selectedConnectors = useMemo(
    () => value.map((id) => allConnectors.find((c) => c.id === id) ?? { id, label: id, category: "general" as const }),
    [value, allConnectors],
  );

  const filteredAvailable = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allConnectors
      .filter((connector) => !selectedSet.has(connector.id))
      .filter((connector) => (q ? connector.label.toLowerCase().includes(q) : true));
  }, [allConnectors, selectedSet, query]);

  function addConnector(id: string) {
    if (selectedSet.has(id)) return;
    onChange([...value, id]);
    setQuery("");
  }

  function removeConnector(id: string) {
    onChange(value.filter((entry) => entry !== id));
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 text-[0.8125rem] text-[var(--text-tertiary)]">
        {t("routines.editor.connectors.description")}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {selectedConnectors.length === 0 ? (
          <span className="text-[0.8125rem] text-[var(--text-quaternary)]">
            {t("routines.editor.connectors.empty")}
          </span>
        ) : (
          selectedConnectors.map((connector) => (
            <span
              key={connector.id}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-2.5 py-1 text-[0.8125rem] text-[var(--text-primary)]"
            >
              <Plug2 className="icon-xs text-[var(--text-tertiary)]" strokeWidth={1.75} />
              <span>{connector.label}</span>
              <button
                type="button"
                aria-label={t("routines.editor.connectors.remove", { label: connector.label })}
                onClick={() => removeConnector(connector.id)}
                disabled={disabled}
                className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <X className="icon-xs" strokeWidth={1.75} />
              </button>
            </span>
          ))
        )}

        <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
          <PopoverTrigger asChild>
            <button
              type="button"
              disabled={disabled || filteredAvailable.length === 0}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-pill)] border border-dashed border-[var(--border-subtle)] bg-transparent px-2.5 text-[0.8125rem] text-[var(--text-secondary)]",
                "transition-[border-color,color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                "hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              <Plus className="icon-xs" strokeWidth={1.75} />
              {t("routines.editor.connectors.addAction")}
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[18rem] p-0">
            <div className="flex items-center gap-2 border-b border-[var(--divider-hair)] px-3">
              <Search className="icon-sm shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("routines.editor.connectors.searchPlaceholder")}
                className="h-9 w-full bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
                spellCheck={false}
                autoCapitalize="off"
                autoCorrect="off"
                autoFocus
              />
            </div>
            <div className="max-h-[14rem] overflow-y-auto py-1">
              {filteredAvailable.length === 0 ? (
                <div className="px-3 py-3 text-center text-[0.75rem] text-[var(--text-tertiary)]">
                  {t("routines.editor.connectors.searchEmpty")}
                </div>
              ) : (
                filteredAvailable.map((connector) => (
                  <button
                    key={connector.id}
                    type="button"
                    onClick={() => {
                      addConnector(connector.id);
                      setOpen(false);
                    }}
                    className="flex w-full items-center gap-2 rounded-[var(--radius-chip)] px-2.5 py-1.5 text-left text-[0.8125rem] text-[var(--text-primary)] transition-[background-color] duration-[120ms] hover:bg-[var(--hover-tint)]"
                  >
                    <Plug2 className="icon-xs shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
                    <span className="flex-1 truncate">{connector.label}</span>
                  </button>
                ))
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
