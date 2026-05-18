import { z } from "zod";
import { operationalErrorEnvelopeSchema } from "@/lib/contracts/run-graph";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

const tokenSchema = z
  .string()
  .trim()
  .min(1)
  .max(240)
  .regex(/^[A-Za-z0-9_.:/-]+$/, "Invalid token.");

const timestampSchema = z.string().trim().max(120).nullable().optional();

const redactionSummarySchema = z
  .object({
    count: z.number().int().nonnegative().default(0),
    fields: z.array(safeText(160)).max(100).default([]),
  })
  .passthrough();

export const evalCaseStatusSchema = z.enum([
  "draft",
  "ready",
  "active",
  "archived",
  "disabled",
]);

export const evalRunStatusSchema = z.enum([
  "queued",
  "running",
  "passed",
  "failed",
  "degraded",
  "cancelled",
  "completed",
]);

export const evalCaseResultStatusSchema = z.enum([
  "passed",
  "failed",
  "warning",
  "skipped",
  "error",
  "queued",
  "running",
]);

export const trajectoryExportStatusSchema = z.enum([
  "queued",
  "running",
  "ready",
  "failed",
  "denied",
]);

export const releaseQualityStatusSchema = z.enum([
  "passed",
  "failed",
  "blocked",
  "degraded",
  "unknown",
  "passing",
  "failing",
]);

export const evalMetricSummarySchema = z
  .object({
    total: z.number().int().nonnegative().default(0),
    passed: z.number().int().nonnegative().default(0),
    failed: z.number().int().nonnegative().default(0),
    warning: z.number().int().nonnegative().default(0),
    skipped: z.number().int().nonnegative().default(0),
    score: z.number().min(0).max(1).nullable().optional(),
  })
  .passthrough();

const emptyEvalMetricSummary = {
  total: 0,
  passed: 0,
  failed: 0,
  warning: 0,
  skipped: 0,
  score: null,
};

export const evalFailureSummarySchema = z
  .object({
    kind: z.enum(["tool", "provider", "policy", "output", "redaction", "release", "unknown"]).default("unknown"),
    name: safeText(180).default("unknown"),
    count: z.number().int().nonnegative().default(0),
    severity: z.enum(["info", "warning", "error", "critical"]).default("warning"),
    message: safeContent(800).nullable().optional(),
  })
  .passthrough();

export const evalCaseSchema = z
  .object({
    schema_version: z.literal("eval_case.v1").default("eval_case.v1"),
    case_key: tokenSchema,
    agent_id: safeIdentifier(120),
    title: safeText(220),
    status: evalCaseStatusSchema.default("draft"),
    source: safeText(120).default("manual"),
    source_task_id: z.number().int().positive().nullable().optional(),
    run_id: tokenSchema.nullable().optional(),
    task_kind: safeText(120).default("general"),
    project_key: safeText(160).default(""),
    environment: safeText(160).default(""),
    team: safeText(160).default(""),
    modality: safeText(80).default("text"),
    input_preview: safeContent(2000).default(""),
    expected_output_preview: safeContent(2000).default(""),
    actual_output_preview: safeContent(2000).nullable().optional(),
    expected_sources: z.array(safeText(500)).max(200).default([]),
    expected_layers: z.array(safeText(160)).max(100).default([]),
    tool_expectations: z.array(z.record(z.string(), z.unknown())).max(120).default([]),
    policy_expectations: z.array(z.record(z.string(), z.unknown())).max(120).default([]),
    tags: z.array(safeText(80)).max(80).default([]),
    redactions: redactionSummarySchema.nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).default({}),
    created_at: timestampSchema,
    updated_at: timestampSchema,
  })
  .passthrough();

export const evalCaseResultSchema = z
  .object({
    case_key: tokenSchema,
    title: safeText(220).optional(),
    status: evalCaseResultStatusSchema,
    score: z.number().min(0).max(1).nullable().optional(),
    message: safeContent(1000).nullable().optional(),
    failure_category: safeText(120).nullable().optional(),
    tool_regressions: z.array(safeText(220)).max(100).default([]),
    policy_regressions: z.array(safeText(220)).max(100).default([]),
    trajectory_export_id: tokenSchema.nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export const evalRunSchema = z
  .object({
    schema_version: z.literal("eval_run.v1").default("eval_run.v1"),
    run_id: tokenSchema,
    agent_id: safeIdentifier(120),
    suite_id: tokenSchema.nullable().optional(),
    suite_name: safeText(220).nullable().optional(),
    mode: z.enum(["offline", "provider", "smoke"]).default("offline"),
    status: evalRunStatusSchema,
    strategy: safeText(120).default("offline_replay"),
    summary: evalMetricSummarySchema.default(emptyEvalMetricSummary),
    cases: z.array(evalCaseResultSchema).max(500).default([]),
    top_failures: z.array(evalFailureSummarySchema).max(80).default([]),
    metrics: z.record(z.string(), z.unknown()).default({}),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    started_at: timestampSchema,
    completed_at: timestampSchema,
    created_at: timestampSchema,
  })
  .passthrough();

export const trajectoryExportSchema = z
  .object({
    schema_version: z.literal("trajectory_export.v1").default("trajectory_export.v1"),
    export_id: tokenSchema,
    agent_id: safeIdentifier(120),
    run_id: tokenSchema.nullable().optional(),
    task_id: z.number().int().positive().nullable().optional(),
    status: trajectoryExportStatusSchema,
    format: z.literal("jsonl").default("jsonl"),
    replay_mode: z.literal("offline").default("offline"),
    redaction_applied: z.boolean().default(true),
    provider_calls_disabled: z.boolean().default(true),
    line_count: z.number().int().nonnegative().default(0),
    byte_size: z.number().int().nonnegative().nullable().optional(),
    package_ref: safeText(500).nullable().optional(),
    download_url: z.string().trim().max(1000).nullable().optional(),
    warnings: z.array(safeText(500)).max(120).default([]),
    redactions: redactionSummarySchema.nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    created_at: timestampSchema,
  })
  .passthrough();

export const releaseQualityGateSchema = z
  .object({
    id: tokenSchema,
    title: safeText(220),
    status: releaseQualityStatusSchema,
    summary: safeContent(1000).default(""),
    required: z.boolean().default(true),
    checked_at: timestampSchema,
    detail_ref: z.string().trim().max(500).nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export const releaseQualitySchema = z
  .object({
    schema_version: z.literal("release_quality.v1").default("release_quality.v1"),
    agent_id: safeIdentifier(120).nullable().optional(),
    status: releaseQualityStatusSchema,
    generated_at: timestampSchema,
    gates: z.array(releaseQualityGateSchema).max(120).default([]),
    latest_eval_run: evalRunSchema.nullable().optional(),
    latest_trajectory_export: trajectoryExportSchema.nullable().optional(),
    top_failures: z.array(evalFailureSummarySchema).max(80).default([]),
    metrics: z.record(z.string(), z.unknown()).default({}),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export type EvalCase = z.infer<typeof evalCaseSchema>;
export type EvalRun = z.infer<typeof evalRunSchema>;
export type EvalCaseResult = z.infer<typeof evalCaseResultSchema>;
export type TrajectoryExport = z.infer<typeof trajectoryExportSchema>;
export type ReleaseQuality = z.infer<typeof releaseQualitySchema>;
export type ReleaseQualityStatus = z.infer<typeof releaseQualityStatusSchema>;

export const createEvalFromRunBodySchema = z
  .object({
    task_id: z.number().int().positive(),
    source_task_id: z.number().int().positive().optional(),
    run_id: tokenSchema.optional(),
    title: safeText(220).optional(),
    input_preview: safeContent(2000).optional(),
    expected_output_preview: safeContent(2000).optional(),
    reference_answer: safeContent(2000).optional(),
    status: evalCaseStatusSchema.optional(),
    expected_tool_ids: z.array(safeText(160)).max(120).optional(),
    expected_policy_codes: z.array(safeText(160)).max(120).optional(),
    expected_sources: z.array(safeText(500)).max(200).optional(),
    expected_layers: z.array(safeText(160)).max(100).optional(),
    tags: z.array(safeText(80)).max(80).optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

export const patchEvalCaseBodySchema = z
  .object({
    title: safeText(220).optional(),
    status: evalCaseStatusSchema.optional(),
    expected_output_preview: safeContent(2000).optional(),
    reference_answer: safeContent(2000).optional(),
    tool_expectations: z.array(z.record(z.string(), z.unknown())).max(120).optional(),
    policy_expectations: z.array(z.record(z.string(), z.unknown())).max(120).optional(),
    expected_sources: z.array(safeText(500)).max(200).optional(),
    expected_layers: z.array(safeText(160)).max(100).optional(),
    tags: z.array(safeText(80)).max(80).optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

export const createEvalRunBodySchema = z
  .object({
    mode: z.enum(["offline", "smoke"]).default("offline"),
    suite_id: tokenSchema.optional(),
    suite_name: safeText(220).optional(),
    case_keys: z.array(tokenSchema).max(500).optional(),
    threshold: z.number().min(0).max(1).optional(),
    release_blocking: z.boolean().optional(),
  })
  .passthrough();

export const createTrajectoryExportBodySchema = z
  .object({
    task_id: z.number().int().positive().optional(),
    run_id: tokenSchema.optional(),
    eval_run_id: tokenSchema.optional(),
    case_key: tokenSchema.optional(),
    replay_mode: z.literal("offline").default("offline"),
    format: z.literal("jsonl").default("jsonl"),
    include_artifact_refs: z.boolean().optional(),
  })
  .passthrough();

export function parseEvalCases(raw: unknown): EvalCase[] {
  const items = extractItems(raw, ["cases", "items"]);
  return items.flatMap((item) => {
    const result = evalCaseSchema.safeParse(normalizeEvalCase(item));
    return result.success ? [result.data] : [];
  });
}

export function parseEvalRuns(raw: unknown): EvalRun[] {
  const items = extractItems(raw, ["runs", "items"]);
  return items.flatMap((item) => {
    const result = evalRunSchema.safeParse(normalizeEvalRun(item));
    return result.success ? [result.data] : [];
  });
}

export function parseEvalRun(raw: unknown): EvalRun | null {
  const payload = unwrapSingle(raw, ["run", "eval_run", "item"]);
  const result = evalRunSchema.safeParse(normalizeEvalRun(payload));
  return result.success ? result.data : null;
}

export function parseTrajectoryExport(raw: unknown): TrajectoryExport | null {
  const payload = unwrapSingle(raw, ["trajectory_export", "export", "item"]);
  const result = trajectoryExportSchema.safeParse(normalizeTrajectoryExport(payload));
  return result.success ? result.data : null;
}

export function parseReleaseQuality(raw: unknown): ReleaseQuality | null {
  const payload = unwrapSingle(raw, ["release_quality", "quality", "item"]);
  const result = releaseQualitySchema.safeParse(normalizeReleaseQuality(payload));
  return result.success ? result.data : null;
}

export function evalErrorMessage(raw: unknown, fallback = "Evaluation request failed.") {
  if (raw instanceof Error && raw.message.trim() && raw.message !== "[object Object]") return raw.message;
  const payload = isRecord(raw) && "error" in raw ? raw.error : raw;
  const result = operationalErrorEnvelopeSchema.safeParse(payload);
  if (result.success) return `${result.data.message} ${result.data.user_action}`.trim();
  if (typeof payload === "string" && payload.trim()) return payload;
  return fallback;
}

function normalizeEvalCase(raw: unknown): unknown {
  const item = asRecord(raw);
  if (item.schema_version === "eval_case.v1") return item;
  const metadata = asRecord(item.metadata ?? item.metadata_json);
  const title = asString(item.title) || asString(item.case_key) || "Eval case";
  return {
    ...item,
    schema_version: "eval_case.v1",
    agent_id: item.agent_id,
    title,
    input_preview: item.input_preview ?? item.query_text ?? item.query ?? "",
    expected_output_preview: item.expected_output_preview ?? item.reference_answer ?? "",
    expected_sources: item.expected_sources ?? item.expected_sources_json ?? [],
    expected_layers: item.expected_layers ?? item.expected_layers_json ?? [],
    source: item.source ?? metadata.source ?? (item.source_task_id ? "run" : "legacy"),
    tool_expectations: item.tool_expectations ?? metadata.tool_expectations ?? [],
    policy_expectations: item.policy_expectations ?? metadata.policy_expectations ?? [],
    tags: item.tags ?? metadata.tags ?? [],
    metadata,
  };
}

function normalizeEvalRun(raw: unknown): unknown {
  const item = asRecord(raw);
  if (item.schema_version === "eval_run.v1") return item;
  const metrics = asRecord(item.metrics ?? item.metrics_json ?? item.metrics_payload);
  const taskSuccess = typeof item.task_success_proxy === "number" ? item.task_success_proxy : null;
  const score =
    typeof metrics.score === "number"
      ? metrics.score
      : taskSuccess !== null
        ? Math.max(0, Math.min(1, taskSuccess))
        : null;
  const runId = asString(item.run_id) || (item.id == null ? "" : `eval_run:${String(item.id)}`);
  return {
    ...item,
    schema_version: "eval_run.v1",
    run_id: runId,
    mode: item.mode ?? "offline",
    status: normalizeEvalRunStatus(item.status, score),
    strategy: item.strategy ?? "offline_replay",
    summary: item.summary ?? {
      total: Number(item.total ?? (item.case_key ? 1 : 0)),
      passed: score !== null && score >= 0.8 ? 1 : 0,
      failed: score !== null && score < 0.8 ? 1 : 0,
      warning: 0,
      skipped: 0,
      score,
    },
    cases: item.cases ?? [],
    top_failures: item.top_failures ?? [],
    metrics,
    created_at: item.created_at,
  };
}

function normalizeTrajectoryExport(raw: unknown): unknown {
  const item = asRecord(raw);
  if (item.schema_version === "trajectory_export.v1") return item;
  const exportId = asString(item.export_id) || asString(item.id) || "trajectory_export:pending";
  return {
    ...item,
    schema_version: "trajectory_export.v1",
    export_id: exportId,
    status: item.status ?? "ready",
    format: item.format ?? "jsonl",
    replay_mode: item.replay_mode ?? "offline",
    redaction_applied: item.redaction_applied ?? true,
    provider_calls_disabled: item.provider_calls_disabled ?? true,
    line_count: item.line_count ?? 0,
  };
}

function normalizeReleaseQuality(raw: unknown): unknown {
  const item = asRecord(raw);
  const gates = normalizeReleaseQualityGates(item.gate_items ?? item.gates);
  const topFailures = normalizeFailureSummaries(item.top_failures ?? item.failure_groups);
  return {
    ...item,
    schema_version: "release_quality.v1",
    status: item.status ?? "unknown",
    gates,
    top_failures: topFailures,
    metrics: item.metrics ?? {},
  };
}

function normalizeReleaseQualityGates(raw: unknown): unknown[] {
  const source = Array.isArray(raw)
    ? raw
    : Object.entries(asRecord(raw)).map(([id, value]) => ({
        id,
        ...asRecord(value),
      }));
  return source.map((gate) => {
    const item = asRecord(gate);
    const id = asString(item.id) || "release_gate";
    return {
      ...item,
      id,
      title: item.title ?? id.replaceAll("_", " "),
      summary: item.summary ?? item.message ?? "",
      status: normalizeReleaseQualityStatus(item.status),
    };
  });
}

function normalizeFailureSummaries(raw: unknown): unknown[] {
  return asArray(raw).map((failure) => {
    const item = asRecord(failure);
    const category = asString(item.category);
    const kind = normalizeFailureKind(asString(item.kind) || failureKindFromCategory(category));
    return {
      ...item,
      kind,
      name: item.name ?? (category || kind),
      severity: item.severity ?? (kind === "unknown" ? "warning" : "error"),
    };
  });
}

function normalizeReleaseQualityStatus(value: unknown): z.infer<typeof releaseQualityStatusSchema> {
  const candidate = asString(value);
  if (releaseQualityStatusSchema.safeParse(candidate).success) {
    return candidate as z.infer<typeof releaseQualityStatusSchema>;
  }
  return "unknown";
}

function failureKindFromCategory(category: string): string {
  if (category.includes("tool")) return "tool";
  if (category.includes("provider")) return "provider";
  if (category.includes("policy")) return "policy";
  if (category.includes("redaction")) return "redaction";
  if (category.includes("release")) return "release";
  if (category.includes("output") || category.includes("assert")) return "output";
  return "unknown";
}

function normalizeFailureKind(value: string): z.infer<typeof evalFailureSummarySchema.shape.kind> {
  const result = evalFailureSummarySchema.shape.kind.safeParse(value);
  return result.success ? result.data : "unknown";
}

function normalizeEvalRunStatus(value: unknown, score: number | null): z.infer<typeof evalRunStatusSchema> {
  const candidate = asString(value);
  if (evalRunStatusSchema.safeParse(candidate).success) {
    return candidate as z.infer<typeof evalRunStatusSchema>;
  }
  if (score === null) return "completed";
  return score >= 0.8 ? "passed" : "failed";
}

function extractItems(raw: unknown, keys: string[]): unknown[] {
  if (Array.isArray(raw)) return raw;
  const record = asRecord(raw);
  for (const key of keys) {
    if (Array.isArray(record[key])) return record[key];
  }
  return [];
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function unwrapSingle(raw: unknown, keys: string[]): unknown {
  const record = asRecord(raw);
  for (const key of keys) {
    if (key in record) return record[key];
  }
  return raw;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

registerBodySchema({
  method: "POST",
  match: (segments) =>
    segments.length === 5 &&
    segments[0] === "agents" &&
    segments[2] === "evals" &&
    segments[3] === "cases" &&
    segments[4] === "from-run",
  schema: createEvalFromRunBodySchema,
});

registerBodySchema({
  method: "PATCH",
  match: (segments) =>
    segments.length === 5 &&
    segments[0] === "agents" &&
    segments[2] === "evals" &&
    segments[3] === "cases",
  schema: patchEvalCaseBodySchema,
});

registerBodySchema({
  method: "POST",
  match: (segments) =>
    segments.length === 4 &&
    segments[0] === "agents" &&
    segments[2] === "evals" &&
    segments[3] === "runs",
  schema: createEvalRunBodySchema,
});

registerBodySchema({
  method: "POST",
  match: (segments) =>
    segments.length === 4 &&
    segments[0] === "agents" &&
    segments[2] === "evals" &&
    segments[3] === "trajectory-exports",
  schema: createTrajectoryExportBodySchema,
});
