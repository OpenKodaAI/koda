"use client";

import { useCallback, useEffect, useRef } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";

export type ProviderDownloadJobStatus =
  | "pending"
  | "running"
  | "completed"
  | "error"
  | "cancelled";

export type ProviderDownloadJob = {
  id: string;
  provider_id: string;
  asset_id: string;
  status: ProviderDownloadJobStatus;
  downloaded_bytes: number;
  total_bytes: number;
  progress_percent: number;
  details?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
};

export type ProviderId = "kokoro" | "supertonic" | "whispercpp" | "embedding";

type StartParams = {
  providerId: ProviderId;
  /** Stable key per asset, e.g. "model" or a voice id or whisper variant id. */
  assetKey: string;
  /** Endpoint that creates the job (POST). */
  startEndpoint: string;
  startBody?: unknown;
  /** Toast title (e.g. "Baixando modelo Kokoro"). */
  toastTitle: string;
  /** Message rendered when the job completes successfully. */
  successMessage: string;
  /** Optional async hook called after the job reaches `completed`. */
  onComplete?: (job: ProviderDownloadJob) => void | Promise<void>;
};

type AttachParams = {
  providerId: ProviderId;
  jobId: string;
  assetKey: string;
  toastTitle: string;
  successMessage: string;
};

const POLL_INTERVAL_MS = 1000;
const MAX_BACKOFF_MS = 5000;
const SOFT_FAILURE_WINDOW_MS = 60_000;

function toastIdFor(providerId: string, assetKey: string): string {
  return `download:${providerId}:${assetKey}`;
}

async function fetchJob(
  providerId: ProviderId,
  jobId: string,
): Promise<ProviderDownloadJob> {
  const res = await fetch(
    `/api/control-plane/providers/${providerId}/downloads/${encodeURIComponent(jobId)}`,
    { credentials: "same-origin" },
  );
  if (!res.ok) {
    throw new Error(`download poll failed with status ${res.status}`);
  }
  return (await res.json()) as ProviderDownloadJob;
}

function jobText(job: ProviderDownloadJob, ...keys: string[]): string {
  const topLevel = job as ProviderDownloadJob & Record<string, unknown>;
  const details =
    job.details && typeof job.details === "object"
      ? (job.details as Record<string, unknown>)
      : {};
  for (const key of keys) {
    const value = details[key] ?? topLevel[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

async function responseErrorText(res: Response, fallback: string): Promise<string> {
  const text = await res.text().catch(() => "");
  if (!text.trim()) return fallback;
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === "object") {
      const record = parsed as Record<string, unknown>;
      for (const key of ["error", "message", "detail"]) {
        const value = record[key];
        if (typeof value === "string" && value.trim()) return value;
      }
    }
  } catch {
    // Non-JSON upstream errors are still useful as-is.
  }
  return text;
}

/**
 * Orchestrates a single download lifecycle: kicks off the job via POST,
 * shows a sticky toast, polls progress, and morphs the toast into a
 * success/error toast on settle. Tolerant to transient network drops via
 * exponential backoff.
 */
export function useDownloadJob() {
  const { t } = useAppI18n();
  const { showToast, updateToast } = useToast();
  // Active asset keys (download:<provider>:<asset>) so the UI can disable
  // duplicate buttons while a download is running.
  const activeKeysRef = useRef<Set<string>>(new Set());
  const intervalsRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const intervals = intervalsRef.current;
    return () => {
      Object.values(intervals).forEach((handle) => window.clearInterval(handle));
    };
  }, []);

  const stopPoll = useCallback((toastId: string) => {
    const handle = intervalsRef.current[toastId];
    if (handle) {
      window.clearInterval(handle);
      delete intervalsRef.current[toastId];
    }
  }, []);

  const cancelDownload = useCallback(
    async (providerId: ProviderId, jobId: string, toastId: string) => {
      updateToast(toastId, {
        type: "loading",
        message: t("downloads.canceling"),
        persistent: true,
        action: {
          label: t("downloads.cancelingAction"),
          ariaLabel: t("downloads.cancelingAria"),
          onClick: () => undefined,
          disabled: true,
        },
      });

      try {
        const res = await fetch(
          `/api/control-plane/providers/${providerId}/downloads/${encodeURIComponent(jobId)}/cancel`,
          {
            method: "POST",
            credentials: "same-origin",
          },
        );
        if (!res.ok) {
          throw new Error(
            await responseErrorText(res, `cancel request failed (${res.status})`),
          );
        }
        const job = (await res.json()) as ProviderDownloadJob;
        stopPoll(toastId);
        activeKeysRef.current.delete(toastId);

        if (job.status === "completed") {
          updateToast(toastId, {
            type: "success",
            message: t("downloads.completedBeforeCancel"),
            persistent: false,
            durationMs: 4000,
            progress: undefined,
            action: undefined,
          });
          return;
        }

        updateToast(toastId, {
          type: job.status === "error" ? "error" : "info",
          message:
            job.status === "error"
              ? jobText(job, "last_error") || t("downloads.failed")
              : t("downloads.canceled"),
          persistent: false,
          durationMs: job.status === "error" ? 8000 : 4000,
          progress: undefined,
          action: undefined,
        });
      } catch (err) {
        const message =
          err instanceof Error && err.message.trim()
            ? err.message
            : t("downloads.cancelFailed");
        updateToast(toastId, {
          type: "error",
          message,
          persistent: true,
          action: {
            label: t("downloads.cancelAction"),
            ariaLabel: t("downloads.cancelAria"),
            onClick: () => {
              void cancelDownload(providerId, jobId, toastId);
            },
          },
        });
      }
    },
    [stopPoll, t, updateToast],
  );

  const cancelAction = useCallback(
    (providerId: ProviderId, jobId: string, toastId: string) => ({
      label: t("downloads.cancelAction"),
      ariaLabel: t("downloads.cancelAria"),
      onClick: () => {
        void cancelDownload(providerId, jobId, toastId);
      },
    }),
    [cancelDownload, t],
  );

  const beginPolling = useCallback(
    (
      providerId: ProviderId,
      jobId: string,
      toastId: string,
      successMessage: string,
      onComplete?: StartParams["onComplete"],
    ) => {
      stopPoll(toastId);

      let failureStreak = 0;
      let firstFailureAt: number | null = null;
      let nextPollDelayMs = POLL_INTERVAL_MS;

      const reschedule = (delayMs: number) => {
        intervalsRef.current[toastId] = window.setTimeout(() => {
          void tick();
        }, delayMs);
      };

      const tick = async () => {
        try {
          const job = await fetchJob(providerId, jobId);
          // Reset error state on a successful poll.
          failureStreak = 0;
          firstFailureAt = null;
          nextPollDelayMs = POLL_INTERVAL_MS;

          if (job.status === "running" || job.status === "pending") {
            updateToast(toastId, {
              type: "loading",
              message: "",
              progress: {
                downloaded: job.downloaded_bytes,
                total: job.total_bytes,
              },
              action: cancelAction(providerId, jobId, toastId),
            });
            // Keep polling while the job is in flight.
            reschedule(nextPollDelayMs);
            return;
          }

          if (job.status === "completed") {
            stopPoll(toastId);
            activeKeysRef.current.delete(toastId);
            updateToast(toastId, {
              type: "success",
              message: successMessage,
              persistent: false,
              durationMs: 4000,
              progress: undefined,
              action: undefined,
            });
            if (onComplete) await onComplete(job);
            return;
          }

          stopPoll(toastId);
          activeKeysRef.current.delete(toastId);
          if (job.status === "cancelled") {
            updateToast(toastId, {
              type: "info",
              message: jobText(job, "message") || t("downloads.canceled"),
              persistent: false,
              durationMs: 4000,
              progress: undefined,
              action: undefined,
            });
            return;
          }

          const lastError = jobText(job, "last_error") || t("downloads.failed");
          updateToast(toastId, {
            type: "error",
            message: lastError,
            persistent: false,
            durationMs: 8000,
            progress: undefined,
            action: undefined,
          });
        } catch {
          // Network / 5xx blip. Don't drop the sticky toast — back off.
          failureStreak += 1;
          if (firstFailureAt === null) firstFailureAt = Date.now();
          nextPollDelayMs = Math.min(MAX_BACKOFF_MS, POLL_INTERVAL_MS * 2 ** failureStreak);

          const elapsed = Date.now() - (firstFailureAt ?? Date.now());
          const message =
            elapsed >= SOFT_FAILURE_WINDOW_MS
              ? t("downloads.serverUnresponsive")
              : t("downloads.reconnecting");
          if (failureStreak >= 3) {
            updateToast(toastId, { message, persistent: true });
          }

          stopPoll(toastId);
          reschedule(nextPollDelayMs);
        }
      };

      // Initial tick scheduled normally so we don't double-fire on attach.
      reschedule(POLL_INTERVAL_MS);
    },
    [cancelAction, stopPoll, t, updateToast],
  );

  const start = useCallback(
    async (params: StartParams) => {
      const toastId = toastIdFor(params.providerId, params.assetKey);
      // Open the sticky toast immediately so the operator sees feedback
      // even before the POST returns.
      showToast("0 B / —", "loading", {
        id: toastId,
        title: params.toastTitle,
        persistent: true,
        progress: { downloaded: 0, total: 0 },
      });
      activeKeysRef.current.add(toastId);

      let job: ProviderDownloadJob;
      try {
        const res = await fetch(params.startEndpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: params.startBody === undefined ? undefined : JSON.stringify(params.startBody),
        });
        if (!res.ok && res.status !== 202) {
          throw new Error(
            await responseErrorText(res, `start request failed (${res.status})`),
          );
        }
        job = (await res.json()) as ProviderDownloadJob;
      } catch (err) {
        activeKeysRef.current.delete(toastId);
        updateToast(toastId, {
          type: "error",
          message: err instanceof Error ? err.message : t("downloads.startFailed"),
          persistent: false,
          durationMs: 8000,
          progress: undefined,
          action: undefined,
        });
        return;
      }

      // Already-completed shortcut (file present locally).
      if (job.status === "completed") {
        activeKeysRef.current.delete(toastId);
        updateToast(toastId, {
          type: "success",
          message: params.successMessage,
          persistent: false,
          durationMs: 4000,
          progress: undefined,
          action: undefined,
        });
        if (params.onComplete) await params.onComplete(job);
        return;
      }

      updateToast(toastId, {
        action: cancelAction(params.providerId, job.id, toastId),
      });
      beginPolling(params.providerId, job.id, toastId, params.successMessage, params.onComplete);
    },
    [beginPolling, cancelAction, showToast, t, updateToast],
  );

  const attach = useCallback(
    (params: AttachParams) => {
      const toastId = toastIdFor(params.providerId, params.assetKey);
      if (activeKeysRef.current.has(toastId)) return;
      showToast(t("downloads.resuming"), "loading", {
        id: toastId,
        title: params.toastTitle,
        persistent: true,
        progress: { downloaded: 0, total: 0 },
        action: cancelAction(params.providerId, params.jobId, toastId),
      });
      activeKeysRef.current.add(toastId);
      beginPolling(params.providerId, params.jobId, toastId, params.successMessage);
    },
    [beginPolling, cancelAction, showToast, t],
  );

  const isActive = useCallback(
    (providerId: ProviderId, assetKey: string) =>
      activeKeysRef.current.has(toastIdFor(providerId, assetKey)),
    [],
  );

  return { start, attach, isActive };
}
