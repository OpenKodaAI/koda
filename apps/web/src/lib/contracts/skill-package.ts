import { z } from "zod";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const skillPackageDecisionSchema = z.enum(["allow", "review_required", "deny"]);
export const skillPackageFindingSeveritySchema = z.enum(["info", "warning", "error", "critical"]);
export const skillPackageRecommendationStatusSchema = z.enum([
  "recommended",
  "unreviewed",
  "eval_failed",
  "blocked",
]);
const dottedTokenSchema = z
  .string()
  .trim()
  .min(1)
  .max(160)
  .regex(/^[A-Za-z0-9_.:-]+$/, "Invalid token.");

export const skillPackageErrorSchema = z
  .object({
    code: z.enum([
      "skill.validation_failed",
      "skill.scan_denied",
      "skill.policy_denied",
      "skill.tool_conflict",
      "skill.rollback_unavailable",
    ]),
    category: safeIdentifier(80),
    message: safeContent(1000),
    retryable: z.boolean().default(false),
    user_action: safeText(500),
  })
  .passthrough();

export const skillPackageFindingSchema = z
  .object({
    id: dottedTokenSchema,
    severity: skillPackageFindingSeveritySchema,
    category: safeIdentifier(80),
    message: safeContent(1000),
    path: z.string().trim().max(1000).default(""),
    user_action: safeText(500).default("Review the package before installing."),
  })
  .passthrough();

export const kodaSkillManifestSummarySchema = z
  .object({
    schema_version: z.literal("koda_skill.v1"),
    manifest_kind: z.string().trim().max(80).optional(),
    id: safeIdentifier(80),
    name: safeText(160),
    version: z.string().trim().max(80),
    description: safeContent(1000).default(""),
    author: safeText(160).default("unknown"),
    license: safeText(160).optional(),
    source: z.string().trim().max(1000).optional(),
    permissions: z.record(z.string(), z.unknown()).default({}),
    docs: z.record(z.string(), z.unknown()).default({}),
    skills: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    tools: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    path: z.string().trim().max(1000).optional(),
    manifest_path: z.string().trim().max(1000).optional(),
  })
  .passthrough();

export const skillScanResultSchema = z
  .object({
    schema_version: z.literal("skill_scan.v1"),
    decision: skillPackageDecisionSchema,
    severity: skillPackageFindingSeveritySchema,
    findings: z.array(skillPackageFindingSchema).max(300).default([]),
    permissions_requested: z.record(z.string(), z.unknown()).default({}),
    risk_classes: z.array(safeIdentifier(80)).max(80).default([]),
    redactions: z.array(z.string().trim().max(1000)).max(200).default([]),
    package_hash: z.string().trim().max(128),
    file_hashes: z.record(z.string(), z.string()).default({}),
    scanner_version: dottedTokenSchema,
    package: kodaSkillManifestSummarySchema,
  })
  .passthrough();

export const skillPackageLockSchema = z
  .object({
    schema_version: z.literal("skill_lock.v1"),
    package_id: safeIdentifier(80),
    name: safeText(160),
    version: z.string().trim().max(80),
    description: safeContent(1000).default(""),
    author: safeText(160).default("unknown"),
    source: z.string().trim().max(1000).optional(),
    package_path: z.string().trim().max(1000).optional(),
    manifest_path: z.string().trim().max(1000).optional(),
    package_hash: z.string().trim().max(128),
    agent_id: safeIdentifier(120),
    installed_skills: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    installed_tools: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    scan_summary: z.record(z.string(), z.unknown()).default({}),
    skill_evals: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    recommendation_status: skillPackageRecommendationStatusSchema.optional(),
    eval_summary: z.record(z.string(), z.unknown()).default({}),
    trust_summary: z.record(z.string(), z.unknown()).default({}),
    installed_at: z.string().trim().max(120).optional(),
    rollback_ref: z.string().trim().max(128).nullable().optional(),
    previous_revision: z.record(z.string(), z.unknown()).nullable().optional(),
    run_graph_evidence: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

export const skillRegistryItemSchema = z
  .object({
    schema_version: z.literal("skill_registry.v1"),
    agent_id: safeIdentifier(120),
    package_id: safeIdentifier(80),
    name: safeText(160),
    version: z.string().trim().max(80),
    description: safeContent(1000).default(""),
    source: z.string().trim().max(1000).default(""),
    package_hash: z.string().trim().max(128),
    installed: z.boolean(),
    installed_at: z.string().trim().max(120).default(""),
    recommendation_status: skillPackageRecommendationStatusSchema,
    scan_summary: z.record(z.string(), z.unknown()).default({}),
    eval_summary: z.record(z.string(), z.unknown()).default({}),
    trust_summary: z.record(z.string(), z.unknown()).default({}),
    skills: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    tools: z.array(z.record(z.string(), z.unknown())).max(200).default([]),
    rollback_available: z.boolean().default(false),
    run_graph_evidence: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();

export const skillRegistrySchema = z
  .object({
    schema_version: z.literal("skill_registry.v1"),
    agent_id: safeIdentifier(120),
    items: z.array(skillRegistryItemSchema).max(500).default([]),
  })
  .passthrough();

export type SkillPackageDecision = z.infer<typeof skillPackageDecisionSchema>;
export type SkillPackageFinding = z.infer<typeof skillPackageFindingSchema>;
export type SkillPackageError = z.infer<typeof skillPackageErrorSchema>;
export type SkillPackageRecommendationStatus = z.infer<typeof skillPackageRecommendationStatusSchema>;
export type SkillScanResult = z.infer<typeof skillScanResultSchema>;
export type SkillPackageLock = z.infer<typeof skillPackageLockSchema>;
export type SkillRegistryItem = z.infer<typeof skillRegistryItemSchema>;
export type SkillRegistry = z.infer<typeof skillRegistrySchema>;

export function parseSkillPackageLocks(raw: unknown): SkillPackageLock[] {
  const items = isRecord(raw) && Array.isArray(raw.items) ? raw.items : raw;
  if (!Array.isArray(items)) return [];
  return items.flatMap((item) => {
    const result = skillPackageLockSchema.safeParse(item);
    return result.success ? [result.data] : [];
  });
}

export function parseSkillScanResult(raw: unknown): SkillScanResult | null {
  const payload = isRecord(raw) && "scan" in raw ? raw.scan : raw;
  const result = skillScanResultSchema.safeParse(payload);
  return result.success ? result.data : null;
}

export function parseSkillRegistry(raw: unknown): SkillRegistry {
  const result = skillRegistrySchema.safeParse(raw);
  return result.success ? result.data : { schema_version: "skill_registry.v1", agent_id: "", items: [] };
}

export function parseSkillPackageError(raw: unknown): SkillPackageError | null {
  const payload = isRecord(raw) && "error" in raw ? raw.error : raw;
  const result = skillPackageErrorSchema.safeParse(payload);
  return result.success ? result.data : null;
}

export function skillPackageErrorMessage(raw: unknown, fallback = "Skill package request failed.") {
  const error = parseSkillPackageError(raw);
  if (error) return `${error.message} ${error.user_action}`.trim();
  if (isRecord(raw) && typeof raw.error === "string") return raw.error;
  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
