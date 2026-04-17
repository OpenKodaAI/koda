"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DetailGridProps {
  children: ReactNode;
  columns?: 1 | 2 | 3;
  className?: string;
}

export function DetailGrid({ children, columns = 2, className }: DetailGridProps) {
  const gridCols =
    columns === 1 ? "grid-cols-1" : columns === 2 ? "grid-cols-2" : "grid-cols-3";
  return (
    <dl className={cn("grid gap-x-4 gap-y-3", gridCols, className)}>{children}</dl>
  );
}

interface DetailDatumProps {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}

export function DetailDatum({ label, value, hint, className }: DetailDatumProps) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-0.5", className)}>
      <dt className="font-mono text-[10.5px] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </dt>
      <dd className="m-0 min-w-0 truncate text-[0.8125rem] text-[var(--text-primary)]">
        {value}
      </dd>
      {hint ? (
        <span className="text-[0.6875rem] text-[var(--text-tertiary)]">{hint}</span>
      ) : null}
    </div>
  );
}

interface DetailBlockProps {
  title?: ReactNode;
  meta?: ReactNode;
  monospace?: boolean;
  children: ReactNode;
  className?: string;
}

export function DetailBlock({
  title,
  meta,
  monospace = false,
  children,
  className,
}: DetailBlockProps) {
  return (
    <section className={cn("flex flex-col gap-2", className)}>
      {title || meta ? (
        <header className="flex items-baseline justify-between gap-3">
          {title ? (
            <h4 className="m-0 text-[0.8125rem] font-medium text-[var(--text-primary)]">
              {title}
            </h4>
          ) : <span />}
          {meta ? (
            <span className="font-mono text-[10.5px] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {meta}
            </span>
          ) : null}
        </header>
      ) : null}
      <div
        className={cn(
          "rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-3 text-[0.8125rem] text-[var(--text-secondary)]",
          monospace && "font-mono leading-[1.55]",
        )}
      >
        {children}
      </div>
    </section>
  );
}
