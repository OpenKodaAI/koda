"use client";

import { useEffect, useRef } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
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
  (
    job: ProviderDownloadJob,
    t: (value: string, options?: Record<string, unknown>) => string,
  ) => { toastTitle: string; successMessage: string }
> = {
  kokoro: (job, t) => {
    if (job.asset_id === "model") {
      return {
        toastTitle: t("generated.hooks.baixando_modelo_kokoro_59c3009b"),
        successMessage: t("generated.hooks.modelo_kokoro_pronto_e0158eb3"),
      };
    }
    const details = {
      ...((job.details as Record<string, unknown> | null | undefined) ?? {}),
      ...(job as ProviderDownloadJob & Record<string, unknown>),
    };
    const voiceName = String(details.voice_name ?? job.asset_id);
    return {
      toastTitle: t("generated.hooks.baixando_voz_kokoro_voice_078d9f78", { voice: voiceName }),
      successMessage: t("generated.hooks.voz_voice_disponivel_1bb7f786", { voice: voiceName }),
    };
  },
  supertonic: (job, t) => {
    const details = {
      ...((job.details as Record<string, unknown> | null | undefined) ?? {}),
      ...(job as ProviderDownloadJob & Record<string, unknown>),
    };
    const modelId = String(details.model_id ?? job.asset_id);
    const voiceName = String(details.voice_name ?? "");
    if (voiceName) {
      return {
        toastTitle: t("generated.hooks.baixando_voz_supertonic_voice_0282dcec", { voice: voiceName }),
        successMessage: t("generated.hooks.voz_voice_disponivel_1bb7f786", { voice: voiceName }),
      };
    }
    const label = String(details.title ?? `Supertonic ${modelId}`);
    return {
      toastTitle: t("generated.hooks.baixando_label_d389a088", { label }),
      successMessage: t("generated.hooks.label_pronto_5d02926b", { label }),
    };
  },
  whispercpp: (job, t) => {
    const details = {
      ...((job.details as Record<string, unknown> | null | undefined) ?? {}),
      ...(job as ProviderDownloadJob & Record<string, unknown>),
    };
    const label = String(details.label ?? `Whisper ${job.asset_id}`);
    return {
      toastTitle: t("generated.hooks.baixando_label_d389a088", { label }),
      successMessage: t("generated.hooks.label_pronto_5d02926b", { label }),
    };
  },
  embedding: (job, t) => {
    const details = {
      ...((job.details as Record<string, unknown> | null | undefined) ?? {}),
      ...(job as ProviderDownloadJob & Record<string, unknown>),
    };
    const label = String(details.title ?? details.label ?? `Embedding ${job.asset_id}`);
    return {
      toastTitle: t("generated.hooks.baixando_label_d389a088", { label }),
      successMessage: t("generated.hooks.label_pronto_5d02926b", { label }),
    };
  },
};

/**
 * Polls `/providers/downloads/active` once on mount and every 30s afterwards
 * to rebind sticky toasts to any download that's still running server-side
 * (e.g. after a hard refresh of the page during a long Whisper download).
 */
export function useActiveDownloads() {
  const { t } = useAppI18n();
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
          const labels = resolver(job, t);
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
  }, [attach, isActive, t]);
}
