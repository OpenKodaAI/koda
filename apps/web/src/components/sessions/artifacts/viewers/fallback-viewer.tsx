"use client";

import { Download, Link as LinkIcon } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import { ARTIFACT_KIND_ICON, formatFileSize, readArtifactFilename } from "@/components/sessions/artifacts/artifact-meta";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";

export interface FallbackViewerProps {
  artifact: ArtifactDetail;
  /** Optional banner shown above the actions (e.g. "Too large to preview"). */
  banner?: string;
}

export function FallbackViewer({ artifact, banner }: FallbackViewerProps) {
  const { t } = useAppI18n();
  const { download, isDownloading, error } = useArtifactDownload();
  const Icon = ARTIFACT_KIND_ICON[artifact.kind];
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const size = formatFileSize(artifact.size_bytes);

  const handleCopyUrl = async () => {
    try {
      await navigator.clipboard.writeText(artifact.download_url);
    } catch {
      // Silent — clipboard API may be unavailable
    }
  };

  return (
    <div className="flex flex-col gap-3 px-5 py-6">
      {banner ? (
        <p className="m-0 text-[0.8125rem] text-[var(--text-tertiary)]">{banner}</p>
      ) : null}
      <div className="flex items-start gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] p-4">
        <Icon className="h-5 w-5 shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[var(--text-primary)]">{filename}</span>
          <span className="mt-0.5 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {[artifact.kind.toUpperCase(), artifact.mime_type, size]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      </div>
      {error ? (
        <p className="m-0 text-[0.75rem] text-[var(--tone-danger-dot)]">{error}</p>
      ) : null}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="accent"
          size="sm"
          onClick={() => void download(artifact)}
          disabled={isDownloading}
          aria-busy={isDownloading}
        >
          <Download className="icon-xs" strokeWidth={1.75} aria-hidden />
          {t("sessions.artifacts.download", undefined)}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={handleCopyUrl}>
          <LinkIcon className="icon-xs" strokeWidth={1.75} aria-hidden />
          {t("sessions.artifacts.copyUrl", undefined)}
        </Button>
      </div>
    </div>
  );
}
