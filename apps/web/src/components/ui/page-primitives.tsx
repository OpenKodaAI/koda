"use client";

import type { ReactNode } from "react";
import { Search, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("app-toolbar-card", className)}>{children}</section>;
}

export function PageToolbarRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("app-toolbar-row", className)}>{children}</div>;
}

export function PageToolbarMeta({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("app-filter-row", className)}>{children}</div>;
}

export function SectionActionBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("flex flex-wrap items-center gap-2.5", className)}>{children}</div>;
}

export function PageSection({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("app-section", className)}>{children}</section>;
}

export function PageDataTableShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain", className)}>{children}</div>;
}

export function PageSectionHeader({
  eyebrow,
  title,
  description,
  meta,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "app-section__header",
        (meta || actions) && "lg:flex-row lg:items-end lg:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2 className={cn("app-section__title", eyebrow && "mt-2")}>{title}</h2>
        {description ? <p className="app-section__description">{description}</p> : null}
      </div>

      {meta || actions ? (
        <div className="app-section__meta">
          {meta}
          {actions}
        </div>
      ) : null}
    </div>
  );
}

export function PageStatGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("app-kpi-grid", className)}>{children}</div>;
}

export function PageMetricStrip({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("metric-strip", className)}>{children}</div>;
}

export function PageMetricStripItem({
  label,
  value,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("metric-strip__item", className)}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

export function PageStatCard({
  label,
  value,
  hint,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("app-kpi-card", className)}>
      <p className="app-kpi-card__label">{label}</p>
      <p className="app-kpi-card__value">{value}</p>
      {hint ? <p className="app-kpi-card__hint">{hint}</p> : null}
    </div>
  );
}

export function PageMiniStat({
  label,
  value,
  className,
}: {
  label: string;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("app-mini-stat", className)}>
      <p className="app-mini-stat__label">{label}</p>
      <p className="app-mini-stat__value">{value}</p>
    </div>
  );
}

export function PageEmptyState({
  icon: Icon,
  visual,
  title,
  description,
  actions,
  className,
}: {
  icon?: LucideIcon;
  visual?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("empty-state", className)}>
      {visual ? visual : Icon ? <Icon className="empty-state-icon h-10 w-10" /> : null}
      <p className="empty-state-text">{title}</p>
      {description ? <p className="empty-state-subtext">{description}</p> : null}
      {actions ? <div className="empty-state-actions">{actions}</div> : null}
    </div>
  );
}

export function PageSkeletonPanel({
  className,
}: {
  className?: string;
}) {
  return <div className={cn("glass-card min-h-[280px] p-6", className)} aria-hidden="true" />;
}

export function PageSkeletonSection({
  className,
}: {
  className?: string;
}) {
  return <div className={cn("app-section min-h-[280px] p-5 sm:p-6", className)} aria-hidden="true" />;
}

export function PageSearchField({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <label className={cn("app-search w-full min-w-0 xl:w-[280px] xl:flex-none", className)}>
      <Search className="h-4 w-4 text-[var(--text-quaternary)]" />
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function PageFilterChips({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("app-filter-row w-full", className)}>{children}</div>;
}

export function PageQueryState({
  title,
  description,
  visual,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  visual?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <PageEmptyState
      title={title}
      description={description}
      visual={visual}
      actions={actions}
      className={className}
    />
  );
}
