"use client";

import { Fragment, type ReactNode } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface EntityHeaderProps {
  glyph?: ReactNode;
  color?: string;
  name: ReactNode;
  description?: ReactNode;
  breadcrumb?: BreadcrumbItem[];
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
}

export function EntityHeader({
  glyph,
  color,
  name,
  description,
  breadcrumb = [],
  actions,
  meta,
  className,
}: EntityHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 border-b border-[var(--divider-hair)] pb-6",
        className,
      )}
    >
      {breadcrumb.length > 0 ? (
        <nav
          aria-label="Breadcrumb"
          className="flex flex-wrap items-center gap-1 text-[0.75rem] text-[var(--text-tertiary)]"
        >
          {breadcrumb.map((item, index) => (
            <Fragment key={`${item.label}-${index}`}>
              {index > 0 ? (
                <ChevronRight
                  className="icon-xs text-[var(--text-quaternary)]"
                  strokeWidth={1.75}
                  aria-hidden
                />
              ) : null}
              {item.href ? (
                <Link
                  href={item.href}
                  className="rounded-[var(--radius-panel-sm)] px-1 transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                >
                  {item.label}
                </Link>
              ) : (
                <span className="px-1 text-[var(--text-secondary)]">{item.label}</span>
              )}
            </Fragment>
          ))}
        </nav>
      ) : null}

      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {glyph ? (
            <span
              aria-hidden
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] text-[var(--text-tertiary)]"
              style={color ? { color } : undefined}
            >
              {glyph}
            </span>
          ) : null}
          <div className="flex min-w-0 flex-col gap-1">
            <h1 className="m-0 truncate text-[1.375rem] font-medium leading-[1.15] tracking-[-0.03em] text-[var(--text-primary)]">
              {name}
            </h1>
            {description ? (
              <p className="m-0 max-w-[720px] text-[0.875rem] leading-[1.55] text-[var(--text-secondary)]">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>

      {meta ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.75rem] text-[var(--text-tertiary)]">
          {meta}
        </div>
      ) : null}
    </header>
  );
}
