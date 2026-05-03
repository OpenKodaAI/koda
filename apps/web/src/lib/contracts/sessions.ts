import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Mention + command schemas                                          */
/* ------------------------------------------------------------------ */

export const mentionKindSchema = z.enum(["skill", "mcp"]);

export const mentionSchema = z.object({
  kind: mentionKindSchema,
  slug: z
    .string()
    .trim()
    .min(1)
    .max(64)
    .regex(/^[a-z0-9_\-]+$/, "Mention slug must be lowercase alphanumeric with _ or -."),
});

export type Mention = z.infer<typeof mentionSchema>;

export const composerCommandSchema = z.object({
  id: z.string().trim().min(1).max(64),
  payload: z.record(z.string(), z.unknown()).optional(),
});

export type ComposerCommand = z.infer<typeof composerCommandSchema>;

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const sendSessionMessageBodySchema = z.object({
  text: safeContent(10_000).min(1, "Message text is required."),
  session_id: z.string().trim().max(240).nullable().optional(),
  mentions: z.array(mentionSchema).max(16).optional(),
  command: composerCommandSchema.optional(),
});

/* ------------------------------------------------------------------ */
/*  Registration (dashboard proxy: /agents/{id}/sessions/messages)     */
/* ------------------------------------------------------------------ */

registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 4 &&
    s[0] === "agents" &&
    s[2] === "sessions" &&
    s[3] === "messages",
  schema: sendSessionMessageBodySchema,
});

/* ------------------------------------------------------------------ */
/*  Approvals                                                          */
/* ------------------------------------------------------------------ */

export const approvalDecisionSchema = z.enum([
  "approve",
  "approved",
  "scope",
  "approve_scope",
  "approved_scope",
  "deny",
  "denied",
  "reject",
]);

export const postApprovalBodySchema = z.object({
  decision: approvalDecisionSchema,
  rationale: z.string().trim().max(500).nullable().optional(),
});

registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 4 &&
    s[0] === "agents" &&
    s[2] === "approvals",
  schema: postApprovalBodySchema,
});

export type ApprovalDecision = z.infer<typeof approvalDecisionSchema>;

export interface PendingApprovalRequest {
  envelope?: Record<string, unknown>;
  approval_scope?: Record<string, unknown>;
}

export interface PendingApproval {
  approval_id: string;
  op_type: string;
  agent_id: string | null;
  session_id: string | null;
  chat_id: number | null;
  user_id: number | null;
  description: string;
  preview_text: string | null;
  requests: PendingApprovalRequest[];
  created_at: number | null;
  decision: string | null;
}

/* ------------------------------------------------------------------ */
/*  Runtime session stream event envelope                              */
/* ------------------------------------------------------------------ */

export type SessionStreamEventKind =
  | "task_started"
  | "task_progress"
  | "task_complete"
  | "task_failed"
  | "message_chunk"
  | "tool_call_start"
  | "tool_call_end"
  | "artifact_ready"
  | "approval_required"
  | "approval_resolved"
  | "session_completed"
  | "heartbeat"
  | string;

export interface SessionStreamEvent {
  seq: number;
  type: SessionStreamEventKind;
  task_id: number | null;
  env_id?: number | null;
  attempt?: number | null;
  phase?: string | null;
  severity?: string | null;
  ts?: string | null;
  payload: Record<string, unknown>;
  artifact_refs?: string[];
  resource_snapshot_ref?: string | null;
}

export function isSessionStreamEvent(value: unknown): value is SessionStreamEvent {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.seq === "number" &&
    typeof record.type === "string" &&
    (record.payload === undefined ||
      (typeof record.payload === "object" && record.payload !== null))
  );
}

/* ------------------------------------------------------------------ */
/*  Typed stream payload schemas (narrow, additive)                    */
/* ------------------------------------------------------------------ */

export const messageChunkPayloadSchema = z.object({
  delta: z.string(),
  message_id: z.string().nullable().optional(),
  block_id: z.string().nullable().optional(),
});

export type MessageChunkPayload = z.infer<typeof messageChunkPayloadSchema>;

export const toolCallEndPayloadSchema = z
  .object({
    tool_call_id: z.string().nullable().optional(),
    tool_name: z.string().nullable().optional(),
    kind: z.string().nullable().optional(),
    block: z.record(z.string(), z.unknown()).nullable().optional(),
    artifact_ids: z.array(z.string()).optional(),
  })
  .passthrough();

export type ToolCallEndPayload = z.infer<typeof toolCallEndPayloadSchema>;

const sessionStreamEventEnvelopeSchema = z
  .object({
    seq: z.number().int().nonnegative(),
    type: z.string().min(1),
    task_id: z.number().int().nullable(),
    env_id: z.number().int().nullable().optional(),
    attempt: z.number().int().nullable().optional(),
    phase: z.string().nullable().optional(),
    severity: z.string().nullable().optional(),
    ts: z.string().nullable().optional(),
    payload: z.record(z.string(), z.unknown()).optional(),
    artifact_refs: z.array(z.string()).optional(),
    resource_snapshot_ref: z.string().nullable().optional(),
  })
  .passthrough();

/**
 * Validate a raw SSE event payload. Returns the typed envelope on success,
 * or null on shape mismatch. Payload contents are NOT deeply validated — that
 * happens at the consumer (e.g. artifact_ready uses artifactReadyEventPayloadSchema
 * from contracts/artifacts.ts).
 */
export function parseSessionStreamEvent(value: unknown): SessionStreamEvent | null {
  const result = sessionStreamEventEnvelopeSchema.safeParse(value);
  if (!result.success) return null;
  const data = result.data;
  return {
    seq: data.seq,
    type: data.type as SessionStreamEventKind,
    task_id: data.task_id ?? null,
    env_id: data.env_id ?? null,
    attempt: data.attempt ?? null,
    phase: data.phase ?? null,
    severity: data.severity ?? null,
    ts: data.ts ?? null,
    payload: data.payload ?? {},
    artifact_refs: data.artifact_refs,
    resource_snapshot_ref: data.resource_snapshot_ref ?? null,
  };
}

/* ------------------------------------------------------------------ */
/*  Block submit (interactive generative UI)                           */
/*  POST /agents/{id}/sessions/{sessionId}/blocks/{blockId}/submit     */
/* ------------------------------------------------------------------ */

const blockSubmitValueSchema: z.ZodType<unknown> = z.union([
  z.string().max(10_000),
  z.number(),
  z.boolean(),
  z.null(),
  z.array(z.string().max(2_000)).max(64),
]);

export const blockSubmitBodySchema = z.object({
  block_type: z.enum(["ui_form", "ui_choice", "ui_card"]),
  values: z.record(z.string().max(120), blockSubmitValueSchema),
  action_id: z.string().trim().max(64).optional(),
});

export type BlockSubmitBody = z.infer<typeof blockSubmitBodySchema>;

registerBodySchema({
  method: "POST",
  match: (s) =>
    s.length === 6 &&
    s[0] === "agents" &&
    s[2] === "sessions" &&
    s[4] === "blocks" &&
    s[5] === "submit",
  schema: blockSubmitBodySchema,
});
