import { z } from "zod";

/* ------------------------------------------------------------------ */
/*  Artifact contracts                                                 */
/*                                                                    */
/*  Versioning is additive: new fields use .optional(); breaking      */
/*  changes ship as a new schema name (e.g. artifactDetailV2Schema).  */
/* ------------------------------------------------------------------ */

export const artifactKindSchema = z.enum([
  "image",
  "audio",
  "video",
  "pdf",
  "docx",
  "spreadsheet",
  "text",
  "html",
  "json",
  "yaml",
  "xml",
  "csv",
  "tsv",
  "url",
  "code",
  "file",
]);

export type ArtifactKind = z.infer<typeof artifactKindSchema>;

export const artifactPreviewStateSchema = z.enum([
  "available",
  "too_large",
  "unsupported",
  "error",
]);

export type ArtifactPreviewState = z.infer<typeof artifactPreviewStateSchema>;

export const artifactDetailSchema = z.object({
  id: z.string().trim().min(1).max(240),
  kind: artifactKindSchema,
  label: z.string().trim().max(240).nullable(),
  mime_type: z.string().trim().max(160).nullable(),
  size_bytes: z.number().int().nonnegative().nullable(),
  created_at: z.string().nullable(),
  source_session_id: z.string().nullable().optional(),
  source_execution_id: z.string().nullable().optional(),
  download_url: z.string().trim().min(1).max(2000),
  preview_state: artifactPreviewStateSchema.default("available"),
  domain: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  path: z.string().nullable().optional(),
});

export type ArtifactDetail = z.infer<typeof artifactDetailSchema>;

/*  Stream payload: artifact_ready                                     */

export const artifactReadyEventPayloadSchema = z.object({
  artifact: artifactDetailSchema,
  message_id: z.string().nullable().optional(),
});

export type ArtifactReadyEventPayload = z.infer<typeof artifactReadyEventPayloadSchema>;

export function parseArtifactReadyPayload(
  raw: unknown,
): ArtifactReadyEventPayload | null {
  const result = artifactReadyEventPayloadSchema.safeParse(raw);
  return result.success ? result.data : null;
}

/*  Preview-size limits (defense in depth — also enforced by backend)  */

export const ARTIFACT_PREVIEW_LIMITS = {
  /** code / markdown / text / html / xml */
  text: 5 * 1024 * 1024,
  /** json / yaml */
  structured: 1 * 1024 * 1024,
  /** csv / tsv (also capped by MAX_CSV_ROWS) */
  tabular: 10 * 1024 * 1024,
} as const;

export const MAX_CSV_ROWS = 10_000;
export const CSV_PAGE_SIZE = 200;

/** Pick a preview cap (in bytes) for a given artifact kind. */
export function previewLimitFor(kind: ArtifactKind): number | null {
  switch (kind) {
    case "code":
    case "text":
    case "html":
    case "xml":
      return ARTIFACT_PREVIEW_LIMITS.text;
    case "json":
    case "yaml":
      return ARTIFACT_PREVIEW_LIMITS.structured;
    case "csv":
    case "tsv":
      return ARTIFACT_PREVIEW_LIMITS.tabular;
    default:
      return null;
  }
}

const PREVIEWABLE_KINDS = new Set<ArtifactKind>([
  "code",
  "text",
  "html",
  "xml",
  "json",
  "yaml",
  "csv",
  "tsv",
]);

export function isPreviewableKind(kind: ArtifactKind): boolean {
  return PREVIEWABLE_KINDS.has(kind);
}
