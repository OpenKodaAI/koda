import { z } from "zod";
import { operationalErrorEnvelopeSchema } from "@/lib/contracts/run-graph";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

const timestampSchema = z.string().trim().max(120).nullable().optional();
const jsonObjectSchema = z.record(z.string(), z.unknown());
const routeScoreSchema = z.number().min(0).max(1).nullable().optional();

export const handoffKindSchema = z.enum(["transfer", "consult", "parallel_consult", "return"]);
export const handoffStatusSchema = z.enum([
  "requested",
  "accepted",
  "declined",
  "timed_out",
  "returned",
  "failed",
]);

export const handoffContextPolicySchema = z.enum([
  "minimal",
  "summary",
  "thread_excerpt",
  "artifact_refs",
  "full_room",
]);
export const handoffContextPolicyValueSchema = z.union([
  handoffContextPolicySchema,
  jsonObjectSchema,
]);

export const routeExplanationStatusSchema = z.enum([
  "selected",
  "excluded",
  "fallback",
  "clarification_required",
  "blocked",
  "routed",
  "coordinating",
]);

export const routeExplanationSignalSchema = z
  .object({
    name: safeIdentifier(80),
    score: routeScoreSchema,
    weight: z.number().min(0).max(1).nullable().optional(),
    direction: z.enum(["positive", "negative", "neutral"]).default("neutral"),
    summary: safeContent(600).default(""),
  })
  .passthrough();

export const routeExplanationCandidateSchema = z
  .object({
    agent_id: safeIdentifier(120),
    status: routeExplanationStatusSchema,
    rank: z.number().int().positive().nullable().optional(),
    score: routeScoreSchema,
    confidence: routeScoreSchema,
    reason: safeContent(1000).default(""),
    exclusion_reason: safeText(240).nullable().optional(),
    signals: z.array(routeExplanationSignalSchema).max(80).default([]),
    metadata: jsonObjectSchema.default({}),
  })
  .passthrough();

export const routeExplanationSchema = z
  .object({
    schema_version: z.literal("route_explanation.v1"),
    route_id: safeIdentifier(160).nullable().optional(),
    source: safeIdentifier(120),
    status: routeExplanationStatusSchema,
    selected_agent_ids: z.array(safeIdentifier(120)).max(80).default([]),
    excluded_agent_ids: z.array(safeIdentifier(120)).max(200).default([]),
    confidence: routeScoreSchema,
    reason: safeContent(1200).default(""),
    summary: safeContent(1200).default(""),
    clarification_required: z.boolean().default(false),
    required_tools: z.array(safeIdentifier(160)).max(120).default([]),
    required_skills: z.array(safeIdentifier(160)).max(120).default([]),
    candidates: z.array(routeExplanationCandidateSchema).max(200).default([]),
    run_graph_node_id: safeIdentifier(240).nullable().optional(),
    metadata: jsonObjectSchema.default({}),
  })
  .passthrough();

export const handoffEventSchema = z
  .object({
    schema_version: z.literal("handoff_event.v1"),
    handoff_id: safeIdentifier(160),
    source_agent_id: safeIdentifier(120),
    destination_agent_ids: z.array(safeIdentifier(120)).min(1).max(80),
    reason: safeContent(1200),
    handoff_kind: handoffKindSchema,
    context_policy: handoffContextPolicyValueSchema,
    deadline: timestampSchema,
    return_criteria: z.array(safeContent(600)).min(1).max(40),
    status: handoffStatusSchema,
    active_agent_id: safeIdentifier(120).nullable().optional(),
    coordinator_agent_id: safeIdentifier(120).nullable().optional(),
    parent_handoff_id: safeIdentifier(160).nullable().optional(),
    thread_id: safeIdentifier(160).nullable().optional(),
    squad_id: safeIdentifier(160).nullable().optional(),
    run_graph_node_id: safeIdentifier(240),
    route_explanation: routeExplanationSchema.nullable().optional(),
    transcript_refs: z.array(safeText(500)).max(120).default([]),
    artifact_refs: z.array(safeText(500)).max(120).default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: jsonObjectSchema.default({}),
    created_at: timestampSchema,
    updated_at: timestampSchema,
    returned_at: timestampSchema,
  })
  .passthrough();

export const handoffEventListSchema = z
  .object({
    schema_version: z.literal("handoff_event.v1"),
    items: z.array(handoffEventSchema).max(500),
  })
  .passthrough();

export type HandoffKind = z.infer<typeof handoffKindSchema>;
export type HandoffStatus = z.infer<typeof handoffStatusSchema>;
export type HandoffContextPolicy = z.infer<typeof handoffContextPolicySchema>;
export type HandoffEvent = z.infer<typeof handoffEventSchema>;
export type RouteExplanation = z.infer<typeof routeExplanationSchema>;

export function parseHandoffEvent(raw: unknown): HandoffEvent | null {
  const result = handoffEventSchema.safeParse(raw);
  return result.success ? result.data : null;
}

export function parseHandoffEvents(raw: unknown): HandoffEvent[] {
  const result = handoffEventListSchema.safeParse(raw);
  return result.success ? result.data.items : [];
}

export function parseRouteExplanation(raw: unknown): RouteExplanation | null {
  const result = routeExplanationSchema.safeParse(raw);
  return result.success ? result.data : null;
}
