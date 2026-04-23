import { z } from "zod";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas                                                            */
/* ------------------------------------------------------------------ */

export const sendSessionMessageBodySchema = z.object({
  text: safeContent(10_000).min(1, "Message text is required."),
  session_id: z.string().trim().max(240).nullable().optional(),
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
