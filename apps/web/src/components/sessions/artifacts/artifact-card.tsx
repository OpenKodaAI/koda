"use client";

import { Download } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import { ARTIFACT_KIND_ICON, formatFileSize, readArtifactFilename } from "@/components/sessions/artifacts/artifact-meta";
import { cn } from "@/lib/utils";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";

export interface ArtifactCardProps {
  artifact: ArtifactDetail;
  onOpen?: (artifact: ArtifactDetail) => void;
  className?: string;
}

export function ArtifactCard({ artifact, onOpen, className }: ArtifactCardProps) {
  const { t } = useAppI18n();
  const downloader = useArtifactDownload();
  const Icon = ARTIFACT_KIND_ICON[artifact.kind];
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const size = formatFileSize(artifact.size_bytes);

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2",
        "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[color:var(--border-strong)]",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onOpen?.(artifact)}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <Icon className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" strokeWidth={1.75} />
        <div className="flex min-w-0 flex-1 flex-col items-start">
          <span className="truncate text-[0.8125rem] text-[var(--text-primary)]">
            {filename}
          </span>
          <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {[artifact.kind.toUpperCase(), size].filter(Boolean).join(" · ")}
          </span>
        </div>
      </button>
      <button
        type="button"
        onClick={() => void downloader.download(artifact)}
        disabled={downloader.isDownloading}
        aria-busy={downloader.isDownloading}
        aria-label={t("sessions.artifacts.download", undefined)}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-60"
      >
        <Download className="icon-xs" strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  );
}
