import { z } from "zod";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const mcpRiskClassSchema = z.enum([
  "read_context",
  "low_risk_write",
  "network_write",
  "destructive_write",
  "secret_access",
  "code_execution",
  "unknown",
]);

export const mcpRiskTagSchema = z.string().trim().min(1).max(80);

export const mcpApprovalDefaultSchema = z.enum(["allow", "allow_with_preview", "require_approval", "ask", "block"]);

export const mcpGrantStateSchema = z.enum([
  "granted",
  "requires_approval",
  "blocked",
  "unknown",
]);

export const mcpCapabilityRiskSchema = z
  .object({
    taxonomy_version: z.literal("mcp_risk.v1"),
    capability_kind: z.enum(["tool", "resource", "prompt"]),
    capability_name: z.string().trim().min(1).max(240),
    risk_class: mcpRiskClassSchema,
    risk_tags: z.array(mcpRiskTagSchema).max(16).default([]),
    approval_default: mcpApprovalDefaultSchema,
    grant_state: mcpGrantStateSchema,
    redaction_required: z.boolean().default(false),
    policy_source: safeIdentifier(120).nullable().optional(),
    policy_ref: z.string().trim().max(500).nullable().optional(),
    rationale: safeContent(800).nullable().optional(),
    warning: safeText(300).nullable().optional(),
  })
  .passthrough();

export type McpRiskClass = z.infer<typeof mcpRiskClassSchema>;
export type McpRiskTag = z.infer<typeof mcpRiskTagSchema>;
export type McpApprovalDefault = z.infer<typeof mcpApprovalDefaultSchema>;
export type McpGrantState = z.infer<typeof mcpGrantStateSchema>;
export type McpCapabilityRisk = z.infer<typeof mcpCapabilityRiskSchema>;

export function parseMcpCapabilityRisk(raw: unknown): McpCapabilityRisk | null {
  const result = mcpCapabilityRiskSchema.safeParse(normalizeMcpCapabilityRisk(raw));
  return result.success ? result.data : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeRiskClass(value: unknown): McpRiskClass {
  const normalized = String(value ?? "").trim().toLowerCase().replace(/[-\s]+/g, "_");
  if (normalized === "read" || normalized === "readonly" || normalized === "read_only") return "read_context";
  if (normalized === "write" || normalized === "low_risk" || normalized === "local_write") return "low_risk_write";
  if (normalized === "network" || normalized === "external_write") return "network_write";
  if (normalized === "destructive" || normalized === "delete") return "destructive_write";
  if (normalized === "secret" || normalized === "secrets") return "secret_access";
  if (normalized === "code" || normalized === "command_execution") return "code_execution";
  return mcpRiskClassSchema.safeParse(normalized).success ? (normalized as McpRiskClass) : "unknown";
}

function normalizeApproval(value: unknown): McpApprovalDefault {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "allow") return "allow";
  if (normalized === "allow_with_preview") return "allow_with_preview";
  if (normalized === "block" || normalized === "deny") return "block";
  return "require_approval";
}

function normalizeMcpCapabilityRisk(raw: unknown): unknown {
  const payload = isRecord(raw) ? raw : {};
  if (payload.taxonomy_version === "mcp_risk.v1") {
    return {
      ...payload,
      risk_class: normalizeRiskClass(payload.risk_class),
      approval_default: normalizeApproval(payload.approval_default),
    };
  }
  const riskClass = normalizeRiskClass(payload.risk_class);
  const approvalDefault = normalizeApproval(payload.approval_default);
  const requiresApproval = Boolean(payload.requires_approval_first) || approvalDefault !== "allow";
  return {
    taxonomy_version: "mcp_risk.v1",
    capability_kind: payload.capability_kind ?? "tool",
    capability_name: payload.capability_name ?? payload.name ?? "unknown",
    risk_class: riskClass,
    risk_tags: Array.isArray(payload.reasons) ? payload.reasons : [],
    approval_default: approvalDefault,
    grant_state: requiresApproval ? "requires_approval" : "granted",
    redaction_required: riskClass === "secret_access" || riskClass === "unknown",
    policy_source: payload.policy_source ?? "backend",
    rationale: Array.isArray(payload.evidence) ? payload.evidence.join(", ") : null,
    warning: requiresApproval ? "Requires approval before execution." : null,
  };
}
