import type { SemanticTone } from "@/lib/theme-semantic";
import { translate } from "@/lib/i18n";

const LABELS: Record<string, string> = {
  available: "runtime.labels.available",
  active: "runtime.labels.active",
  cleaning: "runtime.labels.cleaning",
  cleaned: "runtime.labels.cleaned",
  disabled: "runtime.labels.disabled",
  offline: "runtime.labels.offline",
  partial: "runtime.labels.partial",
  retained: "runtime.labels.retained",
  queued: "runtime.labels.queued",
  running: "runtime.labels.running",
  retrying: "runtime.labels.retrying",
  completed: "runtime.labels.completed",
  failed: "runtime.labels.failed",
  cancelled: "runtime.labels.cancelled",
  cancel_requested: "runtime.labels.cancel_requested",
  paused_for_operator: "runtime.labels.paused_for_operator",
  operator_attached: "runtime.labels.operator_attached",
  recoverable_failed_retained: "runtime.labels.recoverable_failed_retained",
  cancel_requested_retained: "runtime.labels.cancel_requested_retained",
  cancelled_retained: "runtime.labels.cancelled_retained",
  save_verified: "runtime.labels.save_verified",
  unavailable: "runtime.labels.unavailable",
  warning: "runtime.labels.warning",
};

export function getRuntimeLabel(value: string | null | undefined) {
  if (!value) return "—";
  const labelKey = LABELS[value];
  if (labelKey) {
    return translate(labelKey);
  }
  return value
    .split(/[_\-.]/g)
    .filter(Boolean)
    .map((chunk) => chunk[0]?.toUpperCase() + chunk.slice(1))
    .join(" ");
}

export function getRuntimeTone(value: string | null | undefined): SemanticTone {
  const normalized = String(value || "").toLowerCase();

  if (
    normalized.includes("failed") ||
    normalized.includes("error") ||
    normalized.includes("cancel")
  ) {
    return "danger";
  }

  if (
    normalized.includes("running") ||
    normalized.includes("active") ||
    normalized.includes("attached") ||
    normalized.includes("live")
  ) {
    return "info";
  }

  if (
    normalized.includes("queued") ||
    normalized.includes("paused") ||
    normalized.includes("clean") ||
    normalized.includes("pending")
  ) {
    return "warning";
  }

  if (normalized.includes("retry")) {
    return "retry";
  }

  if (
    normalized.includes("completed") ||
    normalized.includes("retained") ||
    normalized.includes("saved") ||
    normalized.includes("verified")
  ) {
    return "success";
  }

  return "neutral";
}

export function getRuntimeSeverityTone(value: string | null | undefined): SemanticTone {
  if (value === "error" || value === "critical") return "danger";
  if (value === "warning") return "warning";
  if (value === "success") return "success";
  return "info";
}

export function formatBytes(bytes: number | null | undefined) {
  if (bytes == null || !Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

export function buildClientWebSocketUrl(relayPath: string) {
  if (relayPath.startsWith("ws://") || relayPath.startsWith("wss://")) {
    return relayPath;
  }
  const origin = window.location.origin.replace(/^http/, "ws");
  return new URL(relayPath, `${origin}/`).toString();
}
