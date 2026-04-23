"use client";

import { AlertTriangle, Info, XCircle, CheckCircle2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type InlineAlertTone = "neutral" | "info" | "success" | "warning" | "danger";

interface InlineAlertProps {
  tone?: InlineAlertTone;
  icon?: LucideIcon | null;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

const TONE_STYLES: Record<
  InlineAlertTone,
  { bg: string; border: string; dot: string; text: string }
> = {
  neutral: {
    bg: "var(--panel-soft)",
    border: "var(--border-subtle)",
    dot: "var(--tone-neutral-dot)",
    text: "var(--text-secondary)",
  },
  info: {
    bg: "var(--tone-info-bg)",
    border: "var(--tone-info-border)",
    dot: "var(--tone-info-dot)",
    text: "var(--tone-info-text)",
  },
  success: {
    bg: "var(--tone-success-bg)",
    border: "var(--tone-success-border)",
    dot: "var(--tone-success-dot)",
    text: "var(--tone-success-text)",
  },
  warning: {
    bg: "var(--tone-warning-bg)",
    border: "var(--tone-warning-border)",
    dot: "var(--tone-warning-dot)",
    text: "var(--tone-warning-text)",
  },
  danger: {
    bg: "var(--tone-danger-bg)",
    border: "var(--tone-danger-border)",
    dot: "var(--tone-danger-dot)",
    text: "var(--tone-danger-text)",
  },
};

const DEFAULT_ICONS: Partial<Record<InlineAlertTone, LucideIcon>> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

export function InlineAlert({
  tone = "warning",
  icon,
  action,
  className,
  children,
}: InlineAlertProps) {
  const styles = TONE_STYLES[tone];
  const Icon = icon === null ? null : icon ?? DEFAULT_ICONS[tone] ?? AlertTriangle;

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-panel-sm)] border px-3.5 py-2.5 text-[0.8125rem]",
        className,
      )}
      style={{
        borderColor: styles.border,
        background: styles.bg,
        color: styles.text,
      }}
    >
      {Icon ? (
        <Icon
          className="mt-[2px] h-4 w-4 shrink-0"
          style={{ color: styles.dot }}
          aria-hidden="true"
        />
      ) : null}
      <div className="min-w-0 flex-1 leading-snug">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
