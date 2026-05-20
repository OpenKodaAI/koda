import { z } from "zod";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

const dottedIdentifierSchema = z
  .string()
  .trim()
  .min(1)
  .max(160)
  .regex(/^[A-Za-z0-9_.:-]+$/, "Invalid identifier.");

export const operationalRunStateSchema = z.enum([
  "queued",
  "running",
  "retrying",
  "stalled",
  "degraded",
  "failed",
  "cancelled",
  "completed",
]);

export const legacyRuntimeTaskStateSchema = z.union([
  operationalRunStateSchema,
  z.literal("paused"),
]);

export const operationalErrorCategorySchema = z.enum([
  "configuration",
  "permission",
  "policy_denied",
  "dependency_unavailable",
  "timeout",
  "validation",
  "retryable",
  "non_retryable",
  "internal",
]);

export const operationalErrorEnvelopeSchema = z
  .object({
    code: dottedIdentifierSchema,
    category: operationalErrorCategorySchema,
    message: safeContent(1000),
    retryable: z.boolean(),
    user_action: safeText(400),
    trace_id: z.string().trim().max(240).nullable().optional(),
    run_graph_node_id: z.string().trim().max(240).nullable().optional(),
    detail_ref: z.string().trim().max(500).nullable().optional(),
  })
  .passthrough();

const runGraphNodeTypeValues = [
  "queue_wait",
  "lease_acquire",
  "lease_renew",
  "lease_lost",
  "lease_reaped",
  "model_call",
  "tool_request",
  "tool_result",
  "tool_call",
  "policy_gate",
  "approval_request",
  "approval_decision",
  "dependency_call",
  "breaker_open",
  "retry_scheduled",
  "dlq_inserted",
  "cancellation",
  "resource_cleanup",
  "user_facing_error",
  "child_run",
  "squad_reply",
  "agent_request",
  "agent_followup",
  "reply_obligation",
  "handoff_event",
  "coordinator_synthesis",
  "artifact",
  "cost",
  "context_block",
  "checkpoint",
  "runtime_event",
] as const;

export type RunGraphNodeType = (typeof runGraphNodeTypeValues)[number];

export const runGraphNodeTypeSchema = z.custom<RunGraphNodeType>(
  (value) => typeof value === "string" && [...runGraphNodeTypeValues].includes(value as RunGraphNodeType),
  "Invalid RunGraph node type.",
) as unknown as z.ZodType<RunGraphNodeType> & { options: typeof runGraphNodeTypeValues };
runGraphNodeTypeSchema.options = runGraphNodeTypeValues;

export const runGraphRedactionSummarySchema = z
  .object({
    count: z.number().int().nonnegative(),
    fields: z.array(dottedIdentifierSchema).max(80),
  })
  .passthrough();

export const runGraphNodeSchema = z
  .object({
    id: safeIdentifier(160),
    parent_id: safeIdentifier(160).nullable().optional(),
    type: runGraphNodeTypeSchema,
    label: safeText(160),
    status: operationalRunStateSchema,
    severity: z.enum(["debug", "info", "warning", "error", "critical"]).default("info"),
    agent_id: safeIdentifier(120).nullable().optional(),
    task_id: z.number().int().positive().nullable().optional(),
    attempt: z.number().int().positive().nullable().optional(),
    session_id: z.string().trim().max(240).nullable().optional(),
    runtime_environment_id: z.string().trim().max(240).nullable().optional(),
    started_at: z.string().trim().max(80).nullable().optional(),
    completed_at: z.string().trim().max(80).nullable().optional(),
    duration_ms: z.number().nonnegative().nullable().optional(),
    summary: safeContent(1000).nullable().optional(),
    detail_ref: z.string().trim().max(500).nullable().optional(),
    audit_ref: z.string().trim().max(500).nullable().optional(),
    metric_refs: z.array(z.string().trim().max(240)).max(40).optional(),
    artifact_refs: z.array(z.string().trim().max(240)).max(80).optional(),
    redactions: runGraphRedactionSummarySchema.nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

export const replayAvailabilitySchema = z.enum(["available", "degraded", "unavailable"]);

export const runReplayStepSchema = z
  .object({
    node_id: safeIdentifier(160),
    type: runGraphNodeTypeSchema,
    label: safeText(160),
    status: operationalRunStateSchema,
    input_ref: z.string().trim().max(500).nullable().optional(),
    output_ref: z.string().trim().max(500).nullable().optional(),
    redacted: z.boolean().default(false),
    deterministic: z.boolean().default(true),
    notes: safeContent(600).nullable().optional(),
  })
  .passthrough();

export const runReplayPlanSchema = z
  .object({
    replay_version: z.literal("run_replay.v1"),
    run_id: safeIdentifier(160),
    task_id: z.number().int().positive().nullable().optional(),
    availability: replayAvailabilitySchema,
    mode: z.literal("offline"),
    provider_calls_disabled: z.boolean().default(true),
    redaction_applied: z.boolean().default(true),
    generated_at: z.string().trim().max(80).nullable().optional(),
    steps: z.array(runReplayStepSchema).max(200),
    missing_dependencies: z.array(safeText(200)).max(40).default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export const runGraphSnapshotSchema = z
  .object({
    run_graph_version: z.literal("run_graph.v1"),
    run_id: safeIdentifier(160),
    root_node_id: safeIdentifier(160).nullable().optional(),
    agent_id: safeIdentifier(120).nullable().optional(),
    task_id: z.number().int().positive().nullable().optional(),
    status: operationalRunStateSchema,
    started_at: z.string().trim().max(80).nullable().optional(),
    completed_at: z.string().trim().max(80).nullable().optional(),
    summary: safeContent(1200).nullable().optional(),
    nodes: z.array(runGraphNodeSchema).max(500),
    redactions: runGraphRedactionSummarySchema.nullable().optional(),
    replay: runReplayPlanSchema.nullable().optional(),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export type OperationalRunState = z.infer<typeof operationalRunStateSchema>;
export type LegacyRuntimeTaskState = z.infer<typeof legacyRuntimeTaskStateSchema>;
export type OperationalErrorCategory = z.infer<typeof operationalErrorCategorySchema>;
export type OperationalErrorEnvelope = z.infer<typeof operationalErrorEnvelopeSchema>;
export type RunGraphNode = z.infer<typeof runGraphNodeSchema>;
export type RunGraphSnapshot = z.infer<typeof runGraphSnapshotSchema>;
export type RunReplayPlan = z.infer<typeof runReplayPlanSchema>;
export type ReplayAvailability = z.infer<typeof replayAvailabilitySchema>;

export function parseRunGraphSnapshot(raw: unknown): RunGraphSnapshot | null {
  const result = runGraphSnapshotSchema.safeParse(normalizeRunGraphSnapshot(raw));
  return result.success ? result.data : null;
}

export function parseRunReplayPlan(raw: unknown): RunReplayPlan | null {
  const result = runReplayPlanSchema.safeParse(normalizeRunReplayPlan(raw));
  return result.success ? result.data : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function normalizeState(value: unknown): OperationalRunState {
  const state = asString(value).trim().toLowerCase();
  if (operationalRunStateSchema.safeParse(state).success) return state as OperationalRunState;
  if (state === "blocked" || state === "warning") return "degraded";
  if (state === "info" || state === "success") return "completed";
  return "completed";
}

function normalizeSeverity(status: OperationalRunState): "debug" | "info" | "warning" | "error" | "critical" {
  if (status === "failed") return "error";
  if (status === "retrying" || status === "stalled" || status === "degraded") return "warning";
  return "info";
}

function normalizeRunGraphNodeType(value: unknown): RunGraphNodeType {
  const type = asString(value).trim().toLowerCase();
  if (runGraphNodeTypeSchema.safeParse(type).success) return type as RunGraphNodeType;
  return "runtime_event";
}

function summarizeRedactions(value: unknown): { count: number; fields: string[] } | null {
  const record = asRecord(value);
  const fields = Object.keys(record).slice(0, 80);
  if (typeof record.count === "number" && Array.isArray(record.fields)) {
    return {
      count: Math.max(0, Math.trunc(record.count)),
      fields: record.fields.map((field) => asString(field)).filter(Boolean).slice(0, 80),
    };
  }
  return fields.length ? { count: fields.length, fields } : null;
}

function normalizeBackendNode(raw: unknown): unknown {
  const node = asRecord(raw);
  const status = normalizeState(node.status);
  const metadata = {
    payload: asRecord(node.payload),
    refs: asRecord(node.refs),
    source: node.source,
    ordinal: node.ordinal,
    runtime_event_seq: node.runtime_event_seq,
  };
  return {
    id: node.node_id,
    parent_id: node.parent_node_id ?? null,
    type: normalizeRunGraphNodeType(node.node_type),
    label: node.summary || node.node_type || "RunGraph node",
    status,
    severity: normalizeSeverity(status),
    agent_id: node.agent_id ?? null,
    task_id: node.task_id ?? null,
    attempt: node.attempt ?? null,
    session_id: node.session_id ?? null,
    runtime_environment_id: node.env_id == null ? null : String(node.env_id),
    started_at: node.started_at ?? null,
    completed_at: node.completed_at ?? null,
    duration_ms: node.duration_ms ?? null,
    summary: node.summary ?? null,
    audit_ref: node.audit_event_id == null ? null : String(node.audit_event_id),
    redactions: summarizeRedactions(node.redactions),
    metadata,
  };
}

function normalizeRunGraphSummary(value: unknown): string | null {
  if (typeof value === "string") return value;
  const summary = asRecord(value);
  const nodeCount = typeof summary.node_count === "number" ? summary.node_count : null;
  const edgeCount = typeof summary.edge_count === "number" ? summary.edge_count : null;
  if (nodeCount !== null || edgeCount !== null) {
    return `Task graph: ${nodeCount ?? 0} nodes / ${edgeCount ?? 0} edges`;
  }
  return null;
}

function normalizeRunGraphSnapshot(raw: unknown): unknown {
  const payload = asRecord(raw);
  if (payload.schema_version !== "run_graph.v1") return raw;
  const nodes = asArray(payload.nodes).map(normalizeBackendNode);
  const summary = asRecord(payload.summary);
  return {
    run_graph_version: "run_graph.v1",
    run_id: payload.graph_id,
    root_node_id: asRecord(nodes[0]).id ?? null,
    agent_id: payload.agent_id ?? null,
    task_id: payload.task_id ?? null,
    status: normalizeState(summary.status),
    started_at: asRecord(nodes[0]).started_at ?? null,
    completed_at: asRecord(nodes[nodes.length - 1]).completed_at ?? null,
    summary: normalizeRunGraphSummary(payload.summary),
    nodes,
    redactions: summarizeRedactions(payload.source_refs),
    replay: normalizeRunReplayPlan(payload.replay),
  };
}

function replayStep(nodeId: string, type: RunGraphNodeType, label: string, notes?: string) {
  return {
    node_id: nodeId,
    type,
    label,
    status: "completed",
    redacted: true,
    deterministic: true,
    notes: notes ?? null,
  };
}

function normalizeRunReplayPlan(raw: unknown): unknown {
  const payload = asRecord(raw);
  if (payload.schema_version !== "run_replay.v1") return raw;
  const divergences = asArray(payload.divergences);
  const steps = [
    ...asArray(payload.inputs).map((_, index) =>
      replayStep(`input-${index + 1}`, "context_block", "Recorded input", "Provider calls disabled."),
    ),
    ...asArray(payload.model_outputs).map((_, index) =>
      replayStep(`model-${index + 1}`, "model_call", "Recorded model output", "Offline replay uses saved output."),
    ),
    ...asArray(payload.tool_results).map((item, index) =>
      replayStep(
        `tool-${index + 1}`,
        "tool_result",
        asString(asRecord(item).tool || `Tool result ${index + 1}`),
        "Tool execution is not re-run during offline replay.",
      ),
    ),
    ...asArray(payload.approval_decisions).map((_, index) =>
      replayStep(`approval-${index + 1}`, "approval_decision", "Recorded approval decision"),
    ),
    ...asArray(payload.artifacts).map((_, index) =>
      replayStep(`artifact-${index + 1}`, "artifact", "Recorded artifact reference"),
    ),
  ];
  return {
    replay_version: "run_replay.v1",
    run_id: payload.graph_id,
    task_id: payload.task_id ?? null,
    availability: divergences.length > 0 ? "degraded" : "available",
    mode: "offline",
    provider_calls_disabled: true,
    redaction_applied: true,
    generated_at: payload.generated_at ?? null,
    steps,
    missing_dependencies: divergences.map((item) => asString(asRecord(item).reason || item)).filter(Boolean),
  };
}
