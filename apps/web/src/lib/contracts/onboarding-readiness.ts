import { z } from "zod";
import { operationalErrorEnvelopeSchema } from "@/lib/contracts/run-graph";
import { registerBodySchema } from "@/lib/contracts/proxy-body-schemas";
import { safeContent, safeIdentifier, safeText } from "@/lib/contracts/sanitizers";

export const onboardingReadinessStatusSchema = z.enum([
  "passed",
  "warning",
  "failed",
  "pending",
]);

export const onboardingReadinessCheckSchema = z
  .object({
    key: safeIdentifier(80),
    title: safeText(160),
    status: onboardingReadinessStatusSchema,
    summary: safeContent(1000),
    action_label: safeText(160).default(""),
    action_href: z.string().trim().max(500).default(""),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).default({}),
  })
  .passthrough();

export const onboardingReadinessSchema = z
  .object({
    schema_version: z.literal("onboarding_readiness.v1").default("onboarding_readiness.v1"),
    status: onboardingReadinessStatusSchema,
    primary_agent_id: safeIdentifier(120).or(z.literal("")).default(""),
    generated_at: safeText(120).default(""),
    checks: z.array(onboardingReadinessCheckSchema).max(60).default([]),
    summary: z
      .object({
        passed: z.number().int().nonnegative().default(0),
        warning: z.number().int().nonnegative().default(0),
        failed: z.number().int().nonnegative().default(0),
        pending: z.number().int().nonnegative().default(0),
      })
      .passthrough(),
    actions: z
      .array(
        z
          .object({
            check: safeIdentifier(80),
            label: safeText(160),
            href: z.string().trim().max(500).default(""),
          })
          .passthrough(),
      )
      .max(60)
      .default([]),
    error: operationalErrorEnvelopeSchema.nullable().optional(),
  })
  .passthrough();

export const onboardingFirstTaskBodySchema = z
  .object({
    agent_id: safeIdentifier(120).optional(),
    text: safeContent(2000).optional(),
    session_id: safeText(160).optional(),
  })
  .partial();

export type OnboardingReadiness = z.infer<typeof onboardingReadinessSchema>;
export type OnboardingReadinessCheck = z.infer<typeof onboardingReadinessCheckSchema>;

export function parseOnboardingReadiness(raw: unknown): OnboardingReadiness {
  return onboardingReadinessSchema.parse(raw);
}

registerBodySchema({
  method: "POST",
  match: (segments) => segments.length === 2 && segments[0] === "onboarding" && segments[1] === "first-task",
  schema: onboardingFirstTaskBodySchema,
});
