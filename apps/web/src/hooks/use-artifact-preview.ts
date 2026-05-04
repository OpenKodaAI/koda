"use client";

import { useControlPlaneQuery } from "@/hooks/use-app-query";
import {
  isPreviewableKind,
  previewLimitFor,
  type ArtifactDetail,
} from "@/lib/contracts/artifacts";

export interface ArtifactPreviewState {
  text: string | null;
  /** When true, the artifact is too large for client-side preview. */
  tooLarge: boolean;
  /** When true, the artifact kind is not text-previewable. */
  unsupported: boolean;
  isLoading: boolean;
  error: string | null;
}

async function fetchArtifactText(artifact: ArtifactDetail): Promise<string> {
  const response = await fetch(artifact.download_url, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`Preview unavailable (${response.status})`);
  }
  return await response.text();
}

/**
 * Fetches the artifact body as text when its kind is previewable AND its size
 * is within the per-kind cap. Out-of-band kinds and oversized artifacts return
 * `unsupported` / `tooLarge` flags so the viewer can show a download fallback
 * without paying the network cost.
 */
export function useArtifactPreview(artifact: ArtifactDetail): ArtifactPreviewState {
  const previewable = isPreviewableKind(artifact.kind);
  const limit = previewLimitFor(artifact.kind);
  const tooLarge =
    typeof artifact.size_bytes === "number" &&
    typeof limit === "number" &&
    artifact.size_bytes > limit;

  const enabled = previewable && !tooLarge;

  const query = useControlPlaneQuery<string>({
    tier: "catalog",
    queryKey: ["artifact", "preview", artifact.id],
    enabled,
    queryFn: () => fetchArtifactText(artifact),
    staleTime: Infinity,
    notifyOnChangeProps: ["data", "error"],
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });

  return {
    text: query.data ?? null,
    tooLarge,
    unsupported: !previewable,
    isLoading: enabled && query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
