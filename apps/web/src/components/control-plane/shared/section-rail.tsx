"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SectionRailItem {
  id: string;
  label: string;
  icon?: ReactNode;
}

interface SectionRailProps {
  items: SectionRailItem[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
  scrollRoot?: HTMLElement | null;
  scrollSpy?: boolean;
  className?: string;
}

export function SectionRail({
  items,
  activeId,
  onSelect,
  scrollRoot,
  scrollSpy = true,
  className,
}: SectionRailProps) {
  const [observedId, setObservedId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (!scrollSpy || typeof window === "undefined" || typeof IntersectionObserver === "undefined") {
      return;
    }
    const root = scrollRoot ?? null;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) {
          const id = (visible[0].target as HTMLElement).id;
          if (id) setObservedId(id);
        }
      },
      {
        root,
        rootMargin: "-40% 0px -55% 0px",
        threshold: [0, 0.25, 0.5, 0.75, 1],
      },
    );
    observerRef.current = observer;

    for (const item of items) {
      const element = document.getElementById(item.id);
      if (element) observer.observe(element);
    }

    return () => {
      observer.disconnect();
      observerRef.current = null;
    };
  }, [items, scrollRoot, scrollSpy]);

  const resolvedActive = activeId ?? observedId ?? items[0]?.id ?? null;

  return (
    <nav
      aria-label="Sections"
      className={cn(
        "sticky top-0 flex w-48 shrink-0 flex-col gap-0.5 py-6 pr-2",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.id === resolvedActive;
        return (
          <a
            key={item.id}
            href={`#${item.id}`}
            onClick={(event) => {
              if (onSelect) {
                event.preventDefault();
                onSelect(item.id);
              }
            }}
            aria-current={active ? "true" : undefined}
            className={cn(
              "relative flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-3 py-2",
              "text-[0.8125rem] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              active
                ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                : "text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]",
            )}
          >
            {active ? (
              <span
                aria-hidden
                className="absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-[var(--accent)]"
              />
            ) : null}
            {item.icon ? (
              <span className="text-[var(--text-quaternary)]" aria-hidden>
                {item.icon}
              </span>
            ) : null}
            <span className="truncate">{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
