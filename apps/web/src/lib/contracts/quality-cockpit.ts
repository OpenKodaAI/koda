import { z } from "zod";
import { operationalErrorEnvelopeSchema } from "@/lib/contracts/run-graph";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

const timestampSchema = z.string().trim().max(120).nullable().optional();
const jsonObjectSchema = z.record(z.string(), z.unknown());
const ratioSchema = z.number().min(0).max(1).nullable().optional();
const emptyQualityMetric = {
  failure_count: 0,
  run_count: 0,
  eval_trend: "unknown" as const,
};

export const qualityCockpitStatusSchema = z.enum([
  "healthy",
  "warning",
  "degraded",
  "failing",
  "blocked",
  "unknown",
]);

export const qualityCockpitEntityTypeSchema = z.enum([
  "agent",
  "squad",
  "tool",
  "skill",
  "model",
  "route_source",
]);

export const qualityCockpitRiskClassSchema = z.enum(["low", "medium", "high", "critical"]);
export const qualityCockpitEvalTrendSchema = z.enum(["improving", "flat", "regressing", "unknown"]);

export const qualityCockpitMetricSchema = z
  .object({
    success_rate: ratioSchema,
    failure_count: z.number().int().nonnegative().default(0),
    run_count: z.number().int().nonnegative().default(0),
    cost_usd: z.number().nonnegative().nullable().optional(),
    timeout_rate: ratioSchema,
    eval_trend: qualityCockpitEvalTrendSchema.default("unknown"),
    eval_score: ratioSchema,
    p95_latency_ms: z.number().nonnegative().nullable().optional(),
  })
  .passthrough();

export const qualityCockpitFailureSchema = z
  .object({
    failure_id: safeIdentifier(160),
    status: qualityCockpitStatusSchema,
    risk_class: qualityCockpitRiskClassSchema,
    title: safeText(220),
    summary: safeContent(1200).default(""),
    count: z.number().int().nonnegative().default(1),
    first_seen_at: timestampSchema,
    last_seen_at: timestampSchema,
    run_graph_node_ids: z.array(safeIdentifier(240)).max(200).default([]),
    proposal_id: safeIdentifier(160).nullable().optional(),
    proposal_action_available: z.boolean().default(false),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: jsonObjectSchema.default({}),
  })
  .passthrough();

export const routeQualityHistorySchema = z
  .object({
    schema_version: z.literal("route_outcome.v1"),
    route_source: safeText(160).default("unknown"),
    outcome_count: z.number().int().nonnegative().default(0),
    success_rate: ratioSchema,
    timeout_rate: ratioSchema,
    failure_rate: ratioSchema,
    quality_score: ratioSchema,
    avg_latency_ms: z.number().nonnegative().nullable().optional(),
    cost_usd: z.number().nonnegative().nullable().optional(),
    run_graph_node_ids: z.array(safeIdentifier(240)).max(200).default([]),
  })
  .passthrough();

export const releaseBlockerSchema = z
  .object({
    schema_version: z.literal("release_blocker.v1"),
    blocker_id: safeIdentifier(180),
    gate_id: safeIdentifier(160),
    severity: z.enum(["low", "medium", "high", "critical"]),
    status: qualityCockpitStatusSchema,
    title: safeText(220),
    summary: safeContent(1200).default(""),
    evidence_refs: z.array(jsonObjectSchema).max(200).default([]),
    next_action: safeContent(1000).default(""),
    proposal_action_available: z.boolean().default(false),
    metadata: jsonObjectSchema.default({}),
  })
  .passthrough();

export const qualityCockpitItemSchema = z
  .object({
    entity_type: qualityCockpitEntityTypeSchema,
    entity_id: safeIdentifier(160),
    label: safeText(220),
    status: qualityCockpitStatusSchema,
    risk_class: qualityCockpitRiskClassSchema.default("low"),
    metrics: qualityCockpitMetricSchema.default(emptyQualityMetric),
    failures: z.array(qualityCockpitFailureSchema).max(200).default([]),
    release_gate_ids: z.array(safeIdentifier(160)).max(80).default([]),
    improvement_proposal_ids: z.array(safeIdentifier(160)).max(120).default([]),
    updated_at: timestampSchema,
    metadata: jsonObjectSchema.default({}),
  })
  .passthrough();

export const qualityCockpitGroupSchema = z
  .object({
    entity_type: qualityCockpitEntityTypeSchema,
    label: safeText(160),
    status: qualityCockpitStatusSchema,
    items: z.array(qualityCockpitItemSchema).max(500).default([]),
    metrics: qualityCockpitMetricSchema.default(emptyQualityMetric),
  })
  .passthrough();

export const qualityCockpitSchema = z
  .object({
    schema_version: z.literal("quality_cockpit.v1"),
    generated_at: timestampSchema,
    status: qualityCockpitStatusSchema,
    summary: qualityCockpitMetricSchema.default(emptyQualityMetric),
    groups: z.array(qualityCockpitGroupSchema).max(80).default([]),
    top_failures: z.array(qualityCockpitFailureSchema).max(200).default([]),
    route_quality_history: z.array(routeQualityHistorySchema).max(200).default([]),
    release_blockers: z.array(releaseBlockerSchema).max(200).default([]),
    release_quality_ref: safeText(500).nullable().optional(),
    trajectory_export_refs: z.array(safeText(500)).max(200).default([]),
    metadata: jsonObjectSchema.default({}),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export type QualityCockpitStatus = z.infer<typeof qualityCockpitStatusSchema>;
export type QualityCockpitRiskClass = z.infer<typeof qualityCockpitRiskClassSchema>;
export type QualityCockpitMetric = z.infer<typeof qualityCockpitMetricSchema>;
export type QualityCockpitFailure = z.infer<typeof qualityCockpitFailureSchema>;
export type RouteQualityHistory = z.infer<typeof routeQualityHistorySchema>;
export type ReleaseBlocker = z.infer<typeof releaseBlockerSchema>;
export type QualityCockpitItem = z.infer<typeof qualityCockpitItemSchema>;
export type QualityCockpitGroup = z.infer<typeof qualityCockpitGroupSchema>;
export type QualityCockpit = z.infer<typeof qualityCockpitSchema>;

export function parseQualityCockpit(raw: unknown): QualityCockpit | null {
  const result = qualityCockpitSchema.safeParse(raw);
  return result.success ? result.data : null;
}
