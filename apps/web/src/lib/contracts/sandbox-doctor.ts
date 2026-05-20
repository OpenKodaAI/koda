import { z } from "zod";
import {
  operationalErrorEnvelopeSchema,
  operationalRunStateSchema,
} from "@/lib/contracts/run-graph";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const sandboxPolicyScopeSchema = z.enum([
  "filesystem",
  "network",
  "shell",
  "browser",
  "environment",
  "mount",
  "ttl",
  "approval",
]);

export const sandboxDoctorStatusSchema = z.enum([
  "passed",
  "warning",
  "failed",
  "degraded",
  "unavailable",
]);

export const sandboxDoctorSeveritySchema = z.enum(["info", "warning", "danger"]);

export const sandboxEffectivePolicySchema = z
  .object({
    policy_version: z.string().trim().min(1).max(80).default("sandbox_policy.v1"),
    agent_id: safeIdentifier(120).nullable().optional(),
    task_id: z.number().int().positive().nullable().optional(),
    runtime_state: operationalRunStateSchema.nullable().optional(),
    scopes: z.array(sandboxPolicyScopeSchema).max(16).default([]),
    read_only: z.boolean().nullable().optional(),
    network_mode: z.string().trim().max(80).nullable().optional(),
    shell_mode: z.string().trim().max(80).nullable().optional(),
    browser_mode: z.string().trim().max(80).nullable().optional(),
    ttl_seconds: z.number().int().positive().nullable().optional(),
    policy_ref: z.string().trim().max(500).nullable().optional(),
  })
  .passthrough();

export const sandboxDoctorCheckSchema = z
  .object({
    id: safeIdentifier(160),
    scope: sandboxPolicyScopeSchema,
    title: safeText(160),
    severity: sandboxDoctorSeveritySchema,
    status: sandboxDoctorStatusSchema,
    message: safeContent(800).nullable().optional(),
    user_action: safeText(300).nullable().optional(),
    evidence_ref: z.string().trim().max(500).nullable().optional(),
    run_graph_node_id: z.string().trim().max(240).nullable().optional(),
  })
  .passthrough();

export const sandboxDoctorResultSchema = z
  .object({
    doctor_version: z.literal("sandbox_doctor.v1"),
    status: sandboxDoctorStatusSchema,
    generated_at: z.string().trim().max(80).nullable().optional(),
    agent_id: safeIdentifier(120).nullable().optional(),
    task_id: z.number().int().positive().nullable().optional(),
    effective_policy: sandboxEffectivePolicySchema.nullable().optional(),
    checks: z.array(sandboxDoctorCheckSchema).max(100),
    degraded_components: z.array(safeText(160)).max(40).default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export type SandboxPolicyScope = z.infer<typeof sandboxPolicyScopeSchema>;
export type SandboxDoctorStatus = z.infer<typeof sandboxDoctorStatusSchema>;
export type SandboxDoctorSeverity = z.infer<typeof sandboxDoctorSeveritySchema>;
export type SandboxEffectivePolicy = z.infer<typeof sandboxEffectivePolicySchema>;
export type SandboxDoctorCheck = z.infer<typeof sandboxDoctorCheckSchema>;
export type SandboxDoctorResult = z.infer<typeof sandboxDoctorResultSchema>;

export function parseSandboxDoctorResult(raw: unknown): SandboxDoctorResult | null {
  const result = sandboxDoctorResultSchema.safeParse(raw);
  return result.success ? result.data : null;
}
