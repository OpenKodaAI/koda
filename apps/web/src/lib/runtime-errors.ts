import { translate } from "@/lib/i18n";

export function isTimeoutLikeMessage(message: string | null | undefined) {
  const normalized = String(message || "").toLowerCase();
  return (
    normalized.includes("aborted due to timeout") ||
    normalized.includes("timed out") ||
    normalized.includes("timeout")
  );
}

function formatTimeoutLabel(timeoutMs: number) {
  const seconds = Math.max(1, Math.round(timeoutMs / 1000));
  return `${seconds}s`;
}

export function normalizeRuntimeRequestError(
  error: unknown,
  timeoutMs: number,
  fallback = "Unable to reach runtime endpoint"
) {
  if (error instanceof Error) {
    if (
      error.name === "TimeoutError" ||
      error.name === "AbortError" ||
      isTimeoutLikeMessage(error.message)
    ) {
      return `Runtime request timed out after ${formatTimeoutLabel(timeoutMs)}.`;
    }

    return error.message;
  }

  return fallback;
}

export function humanizeRuntimeAttachError(
  surface: "terminal" | "browser",
  message: string,
  mode: "preview" | "snapshot"
) {
  const normalized = message.toLowerCase();

  if (
    normalized.includes("runtime ui token is not configured") ||
    normalized.includes("invalid runtime token")
  ) {
    return surface === "terminal"
      ? translate("runtime.terminal.previewHeader")
      : translate("runtime.browser.snapshotMetadata");
  }

  if (isTimeoutLikeMessage(message)) {
    return surface === "terminal"
      ? translate("runtime.attach.terminalTimeout")
      : translate("runtime.attach.browserTimeout");
  }

  return mode === "preview"
    ? message ||
        translate("runtime.attach.terminalPreviewFallback")
    : message ||
        translate("runtime.attach.browserSnapshotFallback");
}
