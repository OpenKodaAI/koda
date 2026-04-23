"use client";

import type { ReactNode } from "react";
import {
  ExternalLink,
  File,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  ImageIcon,
  Link2,
  PlayCircle,
  Volume2,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  ExecutionArtifact,
  ExecutionArtifactLinkPreview,
  ExecutionSummary,
} from "@/lib/types";
import { formatRelativeTime, truncateText } from "@/lib/utils";

type ExecutionSummaryLike = ExecutionSummary & { agent_id?: string | null };

export type SessionArtifactItem = ExecutionArtifact & {
  execution: ExecutionSummaryLike;
  activityAt: string | null;
  dedupeKey: string;
};

interface ContextArtifactsProps {
  items: SessionArtifactItem[];
  linkPreviewByUrl: Map<string, ExecutionArtifactLinkPreview | null>;
}

function isHttpUrl(value: string | null | undefined) {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function formatFileSize(sizeBytes: number | null | undefined) {
  if (typeof sizeBytes !== "number" || !Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return null;
  }
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  if (sizeBytes < 1024 * 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(sizeBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function readArtifactFilename(artifact: ExecutionArtifact) {
  const candidate = artifact.path || artifact.url || artifact.label;
  if (!candidate) return null;
  try {
    const parsed = candidate.startsWith("http") ? new URL(candidate) : null;
    const pathname = parsed ? parsed.pathname : candidate;
    const fileName = pathname.split("/").filter(Boolean).pop();
    return fileName || candidate;
  } catch {
    const fileName = candidate.split("/").filter(Boolean).pop();
    return fileName || candidate;
  }
}

function artifactKindLabel(
  kind: ExecutionArtifact["kind"],
  t: ReturnType<typeof useAppI18n>["t"],
) {
  const fallback = {
    image: "Image",
    audio: "Audio",
    video: "Video",
    pdf: "PDF",
    docx: "Document",
    spreadsheet: "Spreadsheet",
    text: "Text",
    html: "HTML",
    json: "JSON",
    yaml: "YAML",
    xml: "XML",
    csv: "CSV",
    tsv: "TSV",
    url: "Link",
    code: "Code",
    file: "File",
  }[kind];
  return t(`sessions.context.artifacts.kind.${kind}`, { defaultValue: fallback });
}

function ArtifactKindGlyph({ kind }: { kind: ExecutionArtifact["kind"] }) {
  const className = "h-4 w-4 text-[var(--text-tertiary)]";
  switch (kind) {
    case "image":
      return <ImageIcon className={className} strokeWidth={1.75} />;
    case "video":
      return <PlayCircle className={className} strokeWidth={1.75} />;
    case "audio":
      return <Volume2 className={className} strokeWidth={1.75} />;
    case "spreadsheet":
    case "csv":
    case "tsv":
      return <FileSpreadsheet className={className} strokeWidth={1.75} />;
    case "json":
    case "yaml":
    case "xml":
    case "html":
      return <FileJson className={className} strokeWidth={1.75} />;
    case "code":
      return <FileCode2 className={className} strokeWidth={1.75} />;
    case "url":
      return <Link2 className={className} strokeWidth={1.75} />;
    case "pdf":
    case "docx":
    case "text":
      return <FileText className={className} strokeWidth={1.75} />;
    default:
      return <File className={className} strokeWidth={1.75} />;
  }
}

function resolveArtifactLine(
  artifact: SessionArtifactItem,
  preview: ExecutionArtifactLinkPreview | null,
  t: ReturnType<typeof useAppI18n>["t"],
): { title: string; hint: ReactNode } {
  const title =
    preview?.title ||
    artifact.label ||
    readArtifactFilename(artifact) ||
    artifactKindLabel(artifact.kind, t);
  const domain = preview?.domain || artifact.domain;
  const fileName = readArtifactFilename(artifact);
  const fileSize = formatFileSize(artifact.size_bytes);

  const hint =
    fileSize ||
    domain ||
    (fileName && fileName !== title ? truncateText(fileName, 32) : null) ||
    artifactKindLabel(artifact.kind, t);

  return { title, hint };
}

export function ContextArtifacts({ items, linkPreviewByUrl }: ContextArtifactsProps) {
  const { t } = useAppI18n();

  if (items.length === 0) {
    return null;
  }

  return (
    <section className="px-5 py-5">
      <h4 className="m-0 mb-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {t("sessions.context.artifacts.label", { defaultValue: "Artifacts" })}
      </h4>
      <ol className="flex flex-col">
        {items.map((artifact) => {
          const preview = artifact.url ? linkPreviewByUrl.get(artifact.url) ?? null : null;
          const { title, hint } = resolveArtifactLine(artifact, preview, t);
          const externalUrl =
            (preview?.final_url && isHttpUrl(preview.final_url) ? preview.final_url : null) ||
            (artifact.url && isHttpUrl(artifact.url) ? artifact.url : null);

          const content = (
            <>
              <ArtifactKindGlyph kind={artifact.kind} />
              <div className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left">
                <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">
                  {title}
                </span>
                <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  {hint}
                </span>
              </div>
              <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {formatRelativeTime(artifact.activityAt)}
              </span>
              {externalUrl ? (
                <ExternalLink
                  className="h-3 w-3 shrink-0 text-[var(--text-quaternary)]"
                  strokeWidth={1.75}
                  aria-hidden
                />
              ) : null}
            </>
          );

          return (
            <li
              key={artifact.dedupeKey}
              className="border-b border-[color:var(--divider-hair)] last:border-b-0"
            >
              {externalUrl ? (
                <a
                  href={externalUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 py-2.5 transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-[var(--text-primary)]"
                  aria-label={t("sessions.context.artifacts.openExternal", {
                    defaultValue: "Open in a new tab",
                  })}
                >
                  {content}
                </a>
              ) : (
                <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 py-2.5">
                  {content}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
