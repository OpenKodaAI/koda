"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface SoftTabItem {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
}

export interface SoftTabsProps {
  items: SoftTabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
  ariaLabel?: string;
}

export function SoftTabs({ items, value, onChange, className, ariaLabel }: SoftTabsProps) {
  const tabRefs = React.useRef<Record<string, HTMLButtonElement | null>>({});

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") {
      return;
    }
    event.preventDefault();
    let nextIndex = index;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + items.length) % items.length;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % items.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = items.length - 1;
    const nextId = items[nextIndex]?.id;
    if (nextId) {
      onChange(nextId);
      tabRefs.current[nextId]?.focus();
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex h-9 items-center gap-0.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-0.5",
        className,
      )}
    >
      {items.map((item, index) => {
        const selected = value === item.id;
        return (
          <button
            key={item.id}
            ref={(node) => {
              tabRefs.current[item.id] = node;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-[var(--radius-pill)] border-0 px-3 text-[0.8125rem] font-medium outline-none transition-[color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
              selected
                ? "bg-[var(--panel-strong)] text-[var(--text-primary)]"
                : "bg-transparent text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]",
            )}
          >
            {item.icon ? <span className="inline-flex">{item.icon}</span> : null}
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
