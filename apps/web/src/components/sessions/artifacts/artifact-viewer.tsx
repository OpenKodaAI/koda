"use client";

import { Download, Link as LinkIcon, Loader2 } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import { useArtifactPreview } from "@/hooks/use-artifact-preview";
import { ARTIFACT_KIND_ICON, formatFileSize, readArtifactFilename } from "@/components/sessions/artifacts/artifact-meta";
import { CodeViewer } from "@/components/sessions/artifacts/viewers/code-viewer";
import { CsvViewer } from "@/components/sessions/artifacts/viewers/csv-viewer";
import { FallbackViewer } from "@/components/sessions/artifacts/viewers/fallback-viewer";
import { JsonViewer } from "@/components/sessions/artifacts/viewers/json-viewer";
import { MarkdownViewer } from "@/components/sessions/artifacts/viewers/markdown-viewer";
import { TextViewer } from "@/components/sessions/artifacts/viewers/text-viewer";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";

export interface ArtifactViewerProps {
  artifact: ArtifactDetail;
  /** Render the chrome (header bar with download/copy/close). Defaults to true. */
  showHeader?: boolean;
  onClose?: () => void;
}

export function ArtifactViewer({
  artifact,
  showHeader = true,
  onClose,
}: ArtifactViewerProps) {
  const { t } = useAppI18n();
  const preview = useArtifactPreview(artifact);
  const downloader = useArtifactDownload();
  const Icon = ARTIFACT_KIND_ICON[artifact.kind];
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const size = formatFileSize(artifact.size_bytes);

  const handleCopyUrl = async () => {
    try {
      await navigator.clipboard.writeText(artifact.download_url);
    } catch {
      // ignore
    }
  };

  let body: React.ReactNode;
  if (preview.tooLarge) {
    body = (
      <FallbackViewer
        artifact={artifact}
        banner={t("sessions.artifacts.tooLarge", undefined)}
      />
    );
  } else if (preview.unsupported) {
    body = <FallbackViewer artifact={artifact} />;
  } else if (preview.isLoading) {
    body = (
      <div className="flex items-center justify-center px-5 py-12 text-[var(--text-tertiary)]">
        <Loader2 className="icon-md animate-spin" strokeWidth={1.75} aria-hidden />
      </div>
    );
  } else if (preview.error) {
    body = (
      <FallbackViewer
        artifact={artifact}
        banner={t("sessions.artifacts.previewError", undefined)}
      />
    );
  } else if (preview.text === null) {
    body = <FallbackViewer artifact={artifact} />;
  } else {
    switch (artifact.kind) {
      case "code":
        body = <CodeViewer code={preview.text} filename={filename} />;
        break;
      case "json":
      case "yaml":
        body = <JsonViewer content={preview.text} filename={filename} />;
        break;
      case "csv":
        body = <CsvViewer content={preview.text} filename={filename} delimiter="," />;
        break;
      case "tsv":
        body = <CsvViewer content={preview.text} filename={filename} delimiter="\t" />;
        break;
      case "text":
      case "html":
      case "xml":
        body =
          /\.(md|markdown)$/i.test(filename) ? (
            <MarkdownViewer content={preview.text} filename={filename} />
          ) : (
            <TextViewer text={preview.text} filename={filename} />
          );
        break;
      default:
        body = <FallbackViewer artifact={artifact} />;
    }
  }

  return (
    <div className="flex flex-col">
      {showHeader ? (
        <header className="flex items-center justify-between border-b border-[color:var(--divider-hair)] px-5 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <Icon
              className="h-5 w-5 shrink-0 text-[var(--text-tertiary)]"
              strokeWidth={1.75}
            />
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[0.875rem] text-[var(--text-primary)]">
                {filename}
              </span>
              <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {[artifact.kind.toUpperCase(), artifact.mime_type, size]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleCopyUrl}
              aria-label={t("sessions.artifacts.copyUrl", undefined)}
            >
              <LinkIcon className="icon-xs" strokeWidth={1.75} aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void downloader.download(artifact)}
              disabled={downloader.isDownloading}
              aria-busy={downloader.isDownloading}
              aria-label={t("sessions.artifacts.download", undefined)}
            >
              <Download className="icon-xs" strokeWidth={1.75} aria-hidden />
            </Button>
            {onClose ? (
              <Button type="button" variant="ghost" size="sm" onClick={onClose}>
                {t("common.close", undefined)}
              </Button>
            ) : null}
          </div>
        </header>
      ) : null}
      {body}
    </div>
  );
}
