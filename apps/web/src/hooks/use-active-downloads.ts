"use client";

import { useEffect, useRef } from "react";
import { useDownloadJob, type ProviderDownloadJob, type ProviderId } from "@/hooks/use-download-job";

type ActiveDownloadsResponse = {
  items: ProviderDownloadJob[];
};

/**
 * Per-asset toast metadata. Keep these strings centralized so a hard refresh
 * in the middle of a download rebinds the same human-readable title the user
 * was already looking at — switching providers should not lose context.
 */
const ASSET_LABEL_RESOLVERS: Record<
  ProviderId,
  (job: ProviderDownloadJob) => { toastTitle: string; successMessage: string }
> = {
  kokoro: (job) => {
    if (job.asset_id === "model") {
      return {
        toastTitle: "Baixando modelo Kokoro",
        successMessage: "Modelo Kokoro pronto.",
      };
    }
    const details = (job.details as Record<string, unknown> | null | undefined) ?? {};
    const voiceName = String(details.voice_name ?? job.asset_id);
    return {
      toastTitle: `Baixando voz Kokoro · ${voiceName}`,
      successMessage: `Voz "${voiceName}" disponível.`,
    };
  },
  whispercpp: (job) => {
    const details = (job.details as Record<string, unknown> | null | undefined) ?? {};
    const label = String(details.label ?? `Whisper ${job.asset_id}`);
    return {
      toastTitle: `Baixando ${label}`,
      successMessage: `${label} pronto.`,
    };
  },
  embedding: (job) => {
    const details = (job.details as Record<string, unknown> | null | undefined) ?? {};
    const label = String(details.label ?? `Embedding ${job.asset_id}`);
    return {
      toastTitle: `Baixando ${label}`,
      successMessage: `${label} pronto.`,
    };
  },
};

/**
 * Polls `/providers/downloads/active` once on mount and every 30s afterwards
 * to rebind sticky toasts to any download that's still running server-side
 * (e.g. after a hard refresh of the page during a long Whisper download).
 */
export function useActiveDownloads() {
  const { attach, isActive } = useDownloadJob();
  // Track which jobs we've already attached this session to avoid double
  // toasts when a poll returns the same job twice.
  const attachedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    const sync = async () => {
      try {
        const res = await fetch("/api/control-plane/providers/downloads/active", {
          credentials: "same-origin",
        });
        if (!res.ok) return;
        const payload = (await res.json()) as ActiveDownloadsResponse;
        if (cancelled) return;
        for (const job of payload.items ?? []) {
          const providerId = job.provider_id as ProviderId;
          const resolver = ASSET_LABEL_RESOLVERS[providerId];
          if (!resolver) continue;
          if (attachedRef.current.has(job.id)) continue;
          if (isActive(providerId, job.asset_id)) continue;
          const labels = resolver(job);
          attach({
            providerId,
            jobId: job.id,
            assetKey: job.asset_id,
            toastTitle: labels.toastTitle,
            successMessage: labels.successMessage,
          });
          attachedRef.current.add(job.id);
        }
      } catch {
        // Silent: if the endpoint is unreachable we simply don't rebind.
      }
    };

    void sync();
    const handle = window.setInterval(() => void sync(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [attach, isActive]);
}
