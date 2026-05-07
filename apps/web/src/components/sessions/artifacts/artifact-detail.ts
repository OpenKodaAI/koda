import {
  artifactDetailSchema,
  type ArtifactDetail,
} from "@/lib/contracts/artifacts";
import type { ExecutionArtifact } from "@/lib/types";

export function readRuntimeArtifactId(artifact: ExecutionArtifact): string | null {
  const value = artifact.metadata?.runtime_artifact_id;
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

export function runtimeArtifactDownloadUrl(
  runtimeArtifactId: string | null,
  agentId: string | null | undefined,
): string | null {
  if (!runtimeArtifactId || !agentId) return null;
  return `/api/runtime/artifacts/${encodeURIComponent(runtimeArtifactId)}/download?agent=${encodeURIComponent(agentId)}`;
}

export function executionArtifactDedupeKey(artifact: ExecutionArtifact): string {
  return (
    readRuntimeArtifactId(artifact) ||
    artifact.url ||
    artifact.path ||
    artifact.id
  );
}

export function executionArtifactToArtifactDetail(
  artifact: ExecutionArtifact,
  agentId: string | null | undefined,
  activityAt: string | null = null,
): ArtifactDetail | null {
  const runtimeArtifactId = readRuntimeArtifactId(artifact);
  const downloadUrl = runtimeArtifactDownloadUrl(runtimeArtifactId, agentId);
  if (!runtimeArtifactId || !downloadUrl) return null;

  const candidate = {
    id: runtimeArtifactId,
    kind: artifact.kind,
    label: artifact.label ?? null,
    mime_type: artifact.mime_type ?? null,
    size_bytes: artifact.size_bytes ?? null,
    created_at: activityAt,
    source_session_id:
      typeof artifact.metadata?.session_id === "string"
        ? artifact.metadata.session_id
        : null,
    source_execution_id:
      typeof artifact.metadata?.source_execution_id === "string"
        ? artifact.metadata.source_execution_id
        : null,
    download_url: downloadUrl,
    preview_state: "available" as const,
    domain: artifact.domain ?? null,
    url: artifact.url ?? null,
    path: artifact.path ?? null,
  };
  const parsed = artifactDetailSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}
