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
const jsonObjectSchema = z.record(z.string(), z.unknown());
const jsonValueSchema: z.ZodType<unknown> = z.lazy(() =>
  z.union([z.string(), z.number(), z.boolean(), z.null(), z.array(jsonValueSchema), z.record(z.string(), jsonValueSchema)]),
);

export const improvementProposalSourceKindSchema = z.enum([
  "run",
  "eval",
  "user_correction",
  "timeout",
  "dead_letter",
  "tool_failure",
  "manual",
]);

export const improvementProposalTypeSchema = z.enum([
  "memory",
  "skill",
  "prompt",
  "routing_profile",
  "tool_policy",
  "eval_case",
  "docs",
]);

export const improvementProposalRiskClassSchema = z.enum([
  "low",
  "medium",
  "high",
  "critical",
]);

export const improvementProposalStatusSchema = z.enum([
  "draft",
  "pending_review",
  "approved",
  "rejected",
  "validating",
  "applied",
  "rolled_back",
  "failed",
]);

export const improvementProposalStatusHistorySchema = z
  .object({
    status: improvementProposalStatusSchema,
    reviewer: safeText(240).optional(),
    note: safeContent(1000).optional(),
    at: timestampSchema,
    run_graph_node_id: safeIdentifier(240).optional(),
  })
  .passthrough();

export const improvementProposalSchema = z
  .object({
    schema_version: z.literal("improvement_proposal.v1"),
    proposal_id: tokenSchema,
    agent_id: safeIdentifier(120).nullable().optional(),
    source_kind: improvementProposalSourceKindSchema,
    source_ref: safeText(500),
    proposal_type: improvementProposalTypeSchema,
    summary: safeContent(1000),
    evidence_refs: z.array(z.union([safeText(500), jsonObjectSchema])).max(120),
    diff_preview: jsonValueSchema,
    risk_class: improvementProposalRiskClassSchema,
    validation_plan: jsonObjectSchema,
    validation_result: jsonObjectSchema.default({}),
    rollback_plan: jsonObjectSchema,
    status: improvementProposalStatusSchema,
    reviewer: safeText(240).nullable().optional(),
    idempotency_hash: tokenSchema.nullable().optional(),
    run_graph_node_ids: z.array(safeIdentifier(240)).max(200),
    status_history: z.array(improvementProposalStatusHistorySchema).max(200).default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: jsonObjectSchema.default({}),
    created_at: timestampSchema,
    updated_at: timestampSchema,
    reviewed_at: timestampSchema,
    validated_at: timestampSchema,
    applied_at: timestampSchema,
    rolled_back_at: timestampSchema,
  })
  .passthrough();

export const improvementProposalListSchema = z
  .object({
    schema_version: z.literal("improvement_proposal.v1"),
    items: z.array(improvementProposalSchema).max(500),
  })
  .passthrough();

export const improvementProposalActionSchema = z.enum([
  "approve",
  "reject",
  "validate",
  "apply",
  "rollback",
]);

export const improvementProposalActionBodySchema = z
  .object({
    note: safeContent(1000).optional(),
    reviewer: safeText(240).optional(),
    validation_result: jsonObjectSchema.optional(),
  })
  .passthrough();

export type ImprovementProposal = z.infer<typeof improvementProposalSchema>;
export type ImprovementProposalStatus = z.infer<typeof improvementProposalStatusSchema>;
export type ImprovementProposalAction = z.infer<typeof improvementProposalActionSchema>;

export function parseImprovementProposals(raw: unknown): ImprovementProposal[] {
  const result = improvementProposalListSchema.safeParse(raw);
  return result.success ? result.data.items : [];
}

export function parseImprovementProposal(raw: unknown): ImprovementProposal | null {
  const result = improvementProposalSchema.safeParse(raw);
  return result.success ? result.data : null;
}

export function formatProposalJson(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

registerBodySchema({
  method: "POST",
  match: (segments) =>
    segments.length === 5 &&
    segments[0] === "agents" &&
    segments[2] === "improvement-proposals" &&
    improvementProposalActionSchema.safeParse(segments[4]).success,
  schema: improvementProposalActionBodySchema,
});
