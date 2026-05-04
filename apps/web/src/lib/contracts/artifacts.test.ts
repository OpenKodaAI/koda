import { describe, expect, it } from "vitest";
import {
  ARTIFACT_PREVIEW_LIMITS,
  artifactDetailSchema,
  artifactReadyEventPayloadSchema,
  isPreviewableKind,
  parseArtifactReadyPayload,
  previewLimitFor,
} from "@/lib/contracts/artifacts";

const validDetail = {
  id: "art_42",
  kind: "code" as const,
  label: "agent.py",
  mime_type: "text/x-python",
  size_bytes: 1024,
  created_at: "2026-05-02T12:00:00Z",
  download_url: "/api/runtime/artifacts/art_42/download",
};

describe("artifactDetailSchema", () => {
  it("accepts a complete record with optional sources", () => {
    const r = artifactDetailSchema.safeParse({
      ...validDetail,
      source_session_id: "sess_1",
      source_execution_id: "exec_1",
      preview_state: "available",
    });
    expect(r.success).toBe(true);
  });

  it("defaults preview_state to 'available'", () => {
    const r = artifactDetailSchema.safeParse(validDetail);
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.preview_state).toBe("available");
  });

  it("rejects unknown kind", () => {
    expect(
      artifactDetailSchema.safeParse({ ...validDetail, kind: "binary" }).success,
    ).toBe(false);
  });

  it("rejects negative size_bytes", () => {
    expect(
      artifactDetailSchema.safeParse({ ...validDetail, size_bytes: -1 }).success,
    ).toBe(false);
  });

  it("rejects empty download_url", () => {
    expect(
      artifactDetailSchema.safeParse({ ...validDetail, download_url: "" }).success,
    ).toBe(false);
  });
});

describe("artifactReadyEventPayloadSchema", () => {
  it("parses a valid payload", () => {
    const r = parseArtifactReadyPayload({ artifact: validDetail, message_id: "m_1" });
    expect(r).not.toBeNull();
    expect(r?.artifact.id).toBe("art_42");
  });

  it("returns null for malformed payload", () => {
    expect(parseArtifactReadyPayload({})).toBeNull();
    expect(parseArtifactReadyPayload({ artifact: { ...validDetail, kind: "binary" } })).toBeNull();
  });

  it("does not require message_id", () => {
    const r = artifactReadyEventPayloadSchema.safeParse({ artifact: validDetail });
    expect(r.success).toBe(true);
  });
});

describe("previewLimitFor", () => {
  it("maps text kinds to the 5MB cap", () => {
    expect(previewLimitFor("code")).toBe(ARTIFACT_PREVIEW_LIMITS.text);
    expect(previewLimitFor("text")).toBe(ARTIFACT_PREVIEW_LIMITS.text);
    expect(previewLimitFor("xml")).toBe(ARTIFACT_PREVIEW_LIMITS.text);
  });

  it("maps structured kinds to 1MB cap", () => {
    expect(previewLimitFor("json")).toBe(ARTIFACT_PREVIEW_LIMITS.structured);
    expect(previewLimitFor("yaml")).toBe(ARTIFACT_PREVIEW_LIMITS.structured);
  });

  it("maps tabular kinds to 10MB cap", () => {
    expect(previewLimitFor("csv")).toBe(ARTIFACT_PREVIEW_LIMITS.tabular);
    expect(previewLimitFor("tsv")).toBe(ARTIFACT_PREVIEW_LIMITS.tabular);
  });

  it("returns null for non-previewable kinds", () => {
    expect(previewLimitFor("image")).toBeNull();
    expect(previewLimitFor("pdf")).toBeNull();
    expect(previewLimitFor("video")).toBeNull();
  });
});

describe("isPreviewableKind", () => {
  it("returns true for text/code/structured/tabular kinds", () => {
    expect(isPreviewableKind("code")).toBe(true);
    expect(isPreviewableKind("json")).toBe(true);
    expect(isPreviewableKind("csv")).toBe(true);
  });
  it("returns false for binary kinds", () => {
    expect(isPreviewableKind("image")).toBe(false);
    expect(isPreviewableKind("pdf")).toBe(false);
  });
});
