import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { getCurrentLanguage, translate } from "@/lib/i18n";
import { truncateText } from "@/lib/text";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCost(cost: number | null | undefined, locale = getCurrentLanguage()): string {
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cost != null && cost > 0 && cost < 0.01 ? 4 : 2,
    maximumFractionDigits: cost != null && cost > 0 && cost < 0.01 ? 4 : 2,
  });

  return formatter.format(cost ?? 0);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
}

export function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  const locale = getCurrentLanguage();
  const formatter = new Intl.RelativeTimeFormat(locale, {
    numeric: "auto",
    style: "short",
  });

  if (diffSecs < 60) return translate("common.now");
  if (diffMins < 60) return formatter.format(-diffMins, "minute");
  if (diffHours < 24) return formatter.format(-diffHours, "hour");
  if (diffDays < 7) return formatter.format(-diffDays, "day");
  return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short" }).format(date);
}

export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return "—";
  return new Intl.DateTimeFormat(getCurrentLanguage(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(isoString));
}

export { truncateText };
