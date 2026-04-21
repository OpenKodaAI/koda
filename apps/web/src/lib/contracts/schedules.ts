import { z } from "zod";
import { safeContent, safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas (used by runtime route handlers, not the proxy)            */
/* ------------------------------------------------------------------ */

export const scheduleActionBodySchema = z.object({
  user_id: z.union([z.string().trim().min(1), z.number()]),
}).passthrough();

export const patchScheduleBodySchema = z.object({
  user_id: z.union([z.string().trim().min(1), z.number()]),
  expected_config_version: z.number().int().min(0),
  reason: safeText(500),
  patch: z
    .object({
      trigger_type: z.string().trim().max(60).optional(),
      schedule_expr: z.string().trim().max(120).optional(),
      timezone: z.string().trim().max(60).optional(),
      work_dir: z.string().trim().max(500).optional(),
      provider: z.string().trim().max(60).optional(),
      model: z.string().trim().max(120).optional(),
      notification_policy: z.object({ mode: z.string().max(30) }).passthrough().optional(),
      verification_policy: z.object({ mode: z.string().max(30) }).passthrough().optional(),
      query: safeContent(10_000).optional(),
      text: safeContent(10_000).optional(),
      command: safeContent(10_000).optional(),
      description: safeText(2000).optional(),
    })
    .passthrough(),
}).passthrough();
