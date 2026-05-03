import {
  File,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  ImageIcon,
  Link2,
  PlayCircle,
  Volume2,
  type LucideIcon,
} from "lucide-react";
import type { ArtifactKind } from "@/lib/contracts/artifacts";

export const ARTIFACT_KIND_ICON: Record<ArtifactKind, LucideIcon> = {
  image: ImageIcon,
  audio: Volume2,
  video: PlayCircle,
  spreadsheet: FileSpreadsheet,
  csv: FileSpreadsheet,
  tsv: FileSpreadsheet,
  json: FileJson,
  yaml: FileJson,
  xml: FileJson,
  html: FileJson,
  code: FileCode2,
  url: Link2,
  pdf: FileText,
  docx: FileText,
  text: FileText,
  file: File,
};

export function getArtifactIcon(kind: ArtifactKind): LucideIcon {
  return ARTIFACT_KIND_ICON[kind] ?? File;
}

export function formatFileSize(sizeBytes: number | null | undefined): string | null {
  if (typeof sizeBytes !== "number" || !Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return null;
  }
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  if (sizeBytes < 1024 * 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(sizeBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function readArtifactFilename(args: {
  path?: string | null;
  url?: string | null;
  label?: string | null;
}): string | null {
  const candidate = args.path || args.url || args.label;
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
