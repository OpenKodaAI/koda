"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SuggestionItem {
  id: string;
  label: string;
  description?: string | null;
  iconNode?: ReactNode;
  /** Optional dot/swatch colour rendered before the label. */
  swatchColor?: string | null;
  /** Optional right-aligned meta text (e.g. "skill", "mcp"). */
  meta?: string | null;
}

export interface SuggestionGroup {
  id: string;
  label: string | null;
  items: SuggestionItem[];
}

export interface ComposerSuggestionListProps {
  groups: SuggestionGroup[];
  activeIndex: number;
  onSelect: (item: SuggestionItem, group: SuggestionGroup) => void;
  onHover: (flatIndex: number) => void;
  emptyLabel: string;
  ariaLabel: string;
  /** Stable ID prefix used for item DOM ids — referenced by aria-activedescendant. */
  idPrefix: string;
  listboxId: string;
}

export function flattenGroups(
  groups: SuggestionGroup[],
): { item: SuggestionItem; group: SuggestionGroup; flatIndex: number }[] {
  const out: { item: SuggestionItem; group: SuggestionGroup; flatIndex: number }[] = [];
  let flat = 0;
  for (const group of groups) {
    for (const item of group.items) {
      out.push({ item, group, flatIndex: flat });
      flat += 1;
    }
  }
  return out;
}

export function getOptionId(idPrefix: string, flatIndex: number): string {
  return `${idPrefix}-${flatIndex}`;
}

export function ComposerSuggestionList({
  groups,
  activeIndex,
  onSelect,
  onHover,
  emptyLabel,
  ariaLabel,
  idPrefix,
  listboxId,
}: ComposerSuggestionListProps) {
  const flat = flattenGroups(groups);

  if (flat.length === 0) {
    return (
      <div
        className="px-3 py-3 text-[0.75rem] text-[var(--text-tertiary)]"
        role="status"
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <ul
      id={listboxId}
      role="listbox"
      aria-label={ariaLabel}
      className="flex flex-col gap-0.5 py-1 max-h-[280px] overflow-y-auto"
    >
      {groups.map((group) => {
        if (group.items.length === 0) return null;
        return (
          <li key={group.id} role="presentation" className="contents">
            {group.label ? (
              <div
                role="presentation"
                className="px-2 pt-1.5 pb-0.5 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]"
              >
                {group.label}
              </div>
            ) : null}
            {group.items.map((item) => {
              const entry = flat.find(
                (f) => f.group.id === group.id && f.item.id === item.id,
              );
              if (!entry) return null;
              const isActive = entry.flatIndex === activeIndex;
              const optionId = getOptionId(idPrefix, entry.flatIndex);
              return (
                <li
                  key={item.id}
                  id={optionId}
                  role="option"
                  aria-selected={isActive}
                  onMouseEnter={() => onHover(entry.flatIndex)}
                  onMouseDown={(event) => {
                    // Prevent the textarea from losing focus before onClick fires.
                    event.preventDefault();
                  }}
                  onClick={() => onSelect(item, group)}
                  className={cn(
                    "flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-2 py-1.5 mx-1 text-left text-[0.8125rem] cursor-pointer",
                    "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                    isActive
                      ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {item.iconNode ? (
                    <span className="shrink-0 text-[var(--text-tertiary)]" aria-hidden>
                      {item.iconNode}
                    </span>
                  ) : item.swatchColor ? (
                    <span
                      aria-hidden
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: item.swatchColor }}
                    />
                  ) : null}
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{item.label}</span>
                    {item.description ? (
                      <span className="truncate text-[0.6875rem] text-[var(--text-quaternary)]">
                        {item.description}
                      </span>
                    ) : null}
                  </span>
                  {item.meta ? (
                    <span className="shrink-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
                      {item.meta}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </li>
        );
      })}
    </ul>
  );
}
