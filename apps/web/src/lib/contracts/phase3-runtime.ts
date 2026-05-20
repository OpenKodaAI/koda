import { z } from "zod";
import {
  operationalErrorEnvelopeSchema,
  operationalRunStateSchema,
} from "@/lib/contracts/run-graph";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const childRunContractVersionSchema = z.literal("child_run.v1");
export const contextGovernanceContractVersionSchema = z.literal("context_governance.v1");

export const childRunRecordSchema = z
  .object({
    schema_version: childRunContractVersionSchema.default("child_run.v1"),
    child_run_id: safeIdentifier(180),
    agent_id: safeIdentifier(120).nullable().optional(),
    parent_task_id: z.number().int().positive().nullable().optional(),
    child_task_id: z.number().int().positive().nullable().optional(),
    status: operationalRunStateSchema,
    target_agent_id: safeIdentifier(120).nullable().optional(),
    toolset: safeIdentifier(80).default("read_only"),
    summary: safeContent(1400).nullable().optional(),
    structured_output: z.unknown().nullable().optional(),
    artifacts: z.array(z.unknown()).default([]),
    cost_usd: z.number().nonnegative().nullable().optional(),
    run_graph_node_id: safeIdentifier(180).nullable().optional(),
    warnings: z.array(safeText(240)).default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    request: z.record(z.string(), z.unknown()).optional(),
    context_policy: z.record(z.string(), z.unknown()).optional(),
    context_summary: z.record(z.string(), z.unknown()).optional(),
    available_actions: z.array(z.enum(["cancel", "interrupt", "open_execution"])).default([]),
    created_at: z.string().trim().max(80).nullable().optional(),
    started_at: z.string().trim().max(80).nullable().optional(),
    completed_at: z.string().trim().max(80).nullable().optional(),
    deadline_at: z.string().trim().max(80).nullable().optional(),
  })
  .passthrough();

export const contextGovernanceBlockSchema = z
  .object({
    schema_version: contextGovernanceContractVersionSchema.default("context_governance.v1"),
    block_id: safeIdentifier(180),
    category: safeIdentifier(120),
    source: safeText(220),
    token_estimate: z.number().int().nonnegative(),
    status: z.enum(["included", "dropped", "review_required"]),
    include_reason: safeText(240).nullable().optional(),
    drop_reason: safeText(240).nullable().optional(),
    redaction: safeIdentifier(80).default("metadata_only"),
    risk: safeIdentifier(80).default("low"),
    provenance: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();

export const contextGovernanceSummarySchema = z
  .object({
    block_count: z.number().int().nonnegative().default(0),
    included_count: z.number().int().nonnegative().default(0),
    dropped_count: z.number().int().nonnegative().default(0),
    review_required_count: z.number().int().nonnegative().default(0),
    included_token_estimate: z.number().int().nonnegative().optional(),
    dropped_token_estimate: z.number().int().nonnegative().optional(),
    review_required_token_estimate: z.number().int().nonnegative().optional(),
    max_tokens: z.number().int().nonnegative().optional(),
  })
  .passthrough();

export const contextGovernancePayloadSchema = z
  .object({
    schema_version: contextGovernanceContractVersionSchema.default("context_governance.v1"),
    policy: z.record(z.string(), z.unknown()).optional(),
    summary: contextGovernanceSummarySchema.default({
      block_count: 0,
      included_count: 0,
      dropped_count: 0,
      review_required_count: 0,
    }),
    blocks: z.array(contextGovernanceBlockSchema).max(500).default([]),
  })
  .passthrough();

export type ChildRunRecord = z.infer<typeof childRunRecordSchema>;
export type ContextGovernanceBlock = z.infer<typeof contextGovernanceBlockSchema>;
export type ContextGovernancePayload = z.infer<typeof contextGovernancePayloadSchema>;

export function parseChildRuns(raw: unknown): ChildRunRecord[] {
  const result = z.array(childRunRecordSchema).safeParse(raw);
  return result.success ? result.data : [];
}

export function parseContextGovernancePayload(raw: unknown): ContextGovernancePayload | null {
  const result = contextGovernancePayloadSchema.safeParse(raw);
  return result.success ? result.data : null;
}
