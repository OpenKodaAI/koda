"use client";

import { useCallback, useRef, useState } from "react";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";

interface DownloadOptions {
  /** Override the default download URL when needed. */
  url?: string;
  /** Suggested file name; defaults to label / id. */
  filename?: string;
}

interface UseArtifactDownloadResult {
  download: (artifact: ArtifactDetail, options?: DownloadOptions) => Promise<void>;
  isDownloading: boolean;
  error: string | null;
}

/**
 * Triggers a download of an artifact via fetch + blob -> programmatic <a>.
 * Uses createObjectURL/revokeObjectURL with a one-tick delay so the browser
 * has time to start the download before we revoke.
 */
export function useArtifactDownload(): UseArtifactDownloadResult {
  const [isDownloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inflightRef = useRef(false);

  const download = useCallback(
    async (artifact: ArtifactDetail, options?: DownloadOptions) => {
      if (inflightRef.current) return;
      inflightRef.current = true;
      setDownloading(true);
      setError(null);
      try {
        const url = options?.url ?? artifact.download_url;
        const response = await fetch(url, {
          method: "GET",
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`Download failed (${response.status})`);
        }
        const blob = await response.blob();
        const filename =
          options?.filename ?? artifact.label ?? artifact.id ?? "download";
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = filename;
        anchor.rel = "noopener";
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        // Defer revoke so the browser has dispatched the download.
        setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Download failed";
        setError(message);
      } finally {
        inflightRef.current = false;
        setDownloading(false);
      }
    },
    [],
  );

  return { download, isDownloading, error };
}
