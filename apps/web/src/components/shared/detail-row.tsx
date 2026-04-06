"use client";

import type { ReactNode } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface DetailRowProps {
  label: string;
  children: ReactNode;
  className?: string;
  valueClassName?: string;
}

export function DetailRow({
  label,
  children,
  className,
  valueClassName,
}: DetailRowProps) {
  const { tl } = useAppI18n();

  return (
    <div
      className={cn(
        "app-detail-row rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3.5 transition-[border-color,background-color] duration-200 sm:px-4 sm:py-4",
        className
      )}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {tl(label)}
      </p>
      <div
        className={cn(
          "mt-1.5 break-words text-[13px] leading-6 text-[var(--text-secondary)] sm:text-sm",
          valueClassName
        )}
      >
        {children}
      </div>
    </div>
  );
}
