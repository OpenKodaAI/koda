import type { StatusDotTone } from "@/components/ui/status-dot";
import type { Task } from "@/lib/types";

export type TaskStatus = Task["status"];

export const EXECUTION_STATUS_TONE: Record<TaskStatus, StatusDotTone> = {
  queued: "warning",
  running: "info",
  retrying: "retry",
  stalled: "warning",
  degraded: "warning",
  completed: "success",
  failed: "danger",
  paused: "warning",
  cancelled: "neutral",
};

export const EXECUTION_TONE_BG: Record<StatusDotTone, string> = {
  neutral: "var(--tone-neutral-bg)",
  info: "var(--tone-info-bg)",
  success: "var(--tone-success-bg)",
  warning: "var(--tone-warning-bg)",
  danger: "var(--tone-danger-bg)",
  retry: "var(--tone-retry-bg)",
  accent: "var(--accent-muted)",
};

export const EXECUTION_TONE_BORDER: Record<StatusDotTone, string> = {
  neutral: "var(--tone-neutral-border)",
  info: "var(--tone-info-border)",
  success: "var(--tone-success-border)",
  warning: "var(--tone-warning-border)",
  danger: "var(--tone-danger-border)",
  retry: "var(--tone-retry-border)",
  accent: "var(--accent)",
};

export const EXECUTION_TONE_TEXT: Record<StatusDotTone, string> = {
  neutral: "var(--tone-neutral-muted)",
  info: "var(--tone-info-muted)",
  success: "var(--tone-success-muted)",
  warning: "var(--tone-warning-muted)",
  danger: "var(--tone-danger-muted)",
  retry: "var(--tone-retry-muted)",
  accent: "var(--text-primary)",
};

export const EXECUTION_TONE_DOT: Record<StatusDotTone, string> = {
  neutral: "var(--tone-neutral-dot)",
  info: "var(--tone-info-dot)",
  success: "var(--tone-success-dot)",
  warning: "var(--tone-warning-dot)",
  danger: "var(--tone-danger-dot)",
  retry: "var(--tone-retry-dot)",
  accent: "var(--accent)",
};

export function executionStatusTone(status: string): StatusDotTone {
  return EXECUTION_STATUS_TONE[status as TaskStatus] ?? "neutral";
}

export function isRunningStatus(status: string): boolean {
  return status === "running" || status === "retrying" || status === "stalled";
}
