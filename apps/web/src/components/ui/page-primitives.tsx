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
  return (
    <section className={cn("flex flex-wrap items-center gap-3", className)}>{children}</section>
  );
}

export function PageToolbarRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("flex flex-wrap items-center gap-3", className)}>{children}</div>;
}

export function PageToolbarMeta({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("flex flex-wrap items-center gap-2", className)}>{children}</div>;
}

export function SectionActionBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("flex flex-wrap items-center gap-2", className)}>{children}</div>;
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
  return (
    <div className={cn("max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain", className)}>
      {children}
    </div>
  );
}

export function PageSectionHeader({
  eyebrow,
  title,
  description,
  meta,
  actions,
  compact = false,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "app-section__header",
        (meta || actions) && "lg:flex-row lg:items-end lg:justify-between",
        compact && "gap-1",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2
          className={cn(
            compact ? "m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]" : "app-section__title",
            eyebrow && !compact && "mt-2",
          )}
        >
          {title}
        </h2>
        {description ? (
          <p
            className={cn(
              compact ? "m-0 mt-0.5 text-[0.8125rem] text-[var(--text-tertiary)]" : "app-section__description",
            )}
          >
            {description}
          </p>
        ) : null}
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
  hint,
  delta,
  tone = "neutral",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  delta?: ReactNode;
  tone?: "neutral" | "accent" | "warning" | "danger" | "success";
  className?: string;
}) {
  const toneClass =
    tone === "accent"
      ? "text-[var(--accent)]"
      : tone === "warning"
        ? "text-[var(--tone-warning-dot)]"
        : tone === "danger"
          ? "text-[var(--tone-danger-dot)]"
          : tone === "success"
            ? "text-[var(--tone-success-dot)]"
            : "";

  return (
    <div className={cn("metric-strip__item", className)}>
      <span className="metric-label">{label}</span>
      <span className={cn("metric-value", toneClass)}>{value}</span>
      {hint ? (
        <span className="text-[0.75rem] leading-[1.45] text-[var(--text-tertiary)]">{hint}</span>
      ) : null}
      {delta ? (
        <span className="text-[0.75rem] text-[var(--text-tertiary)]">{delta}</span>
      ) : null}
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
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <label className={cn("app-search w-full min-w-0 xl:w-[280px] xl:flex-none", className)}>
      <Search className="h-4 w-4 text-[var(--text-quaternary)]" />
      <input
        type="text"
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
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
  return <div className={cn("flex flex-wrap items-center gap-2 w-full", className)}>{children}</div>;
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
