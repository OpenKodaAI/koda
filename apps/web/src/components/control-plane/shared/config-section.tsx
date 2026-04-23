"use client";

import { forwardRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ConfigSectionProps {
  id?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export const ConfigSection = forwardRef<HTMLElement, ConfigSectionProps>(function ConfigSection(
  { id, title, description, actions, children, className, bodyClassName },
  ref,
) {
  return (
    <section
      id={id}
      ref={ref}
      className={cn(
        "flex flex-col gap-4 border-b border-[var(--divider-hair)] py-8 first:pt-0 last:border-b-0",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="m-0 text-[0.9375rem] font-medium tracking-[-0.01em] text-[var(--text-primary)]">
            {title}
          </h3>
          {description ? (
            <p className="m-0 max-w-[600px] text-[0.8125rem] leading-[1.5] text-[var(--text-tertiary)]">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className={cn("flex flex-col gap-3", bodyClassName)}>{children}</div>
    </section>
  );
});
