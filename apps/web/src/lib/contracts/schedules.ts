import { z } from "zod";
import { safeContent, safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Schemas (used by runtime route handlers, not the proxy)            */
/* ------------------------------------------------------------------ */

export const scheduleActionBodySchema = z.object({
  user_id: z.union([z.string().trim().min(1), z.number()]),
}).passthrough();

export const createScheduleBodySchema = z.object({
  user_id: z.union([z.string().trim().min(1), z.number()]).optional(),
  chat_id: z.union([z.string().trim().min(1), z.number()]).optional(),
  session_id: z.string().trim().max(120).optional(),
  job_type: z.enum(["agent_query", "reminder", "shell_command"]).default("agent_query"),
  trigger_type: z.enum(["one_shot", "cron", "interval"]),
  schedule_expr: z.string().trim().min(1).max(120),
  timezone: z.string().trim().min(1).max(60),
  payload: z
    .object({
      name: safeText(120).optional(),
      query: safeContent(10_000).optional(),
      text: safeContent(10_000).optional(),
      command: safeContent(10_000).optional(),
      description: safeText(2000).optional(),
      connectors: z.array(z.string().trim().max(120)).max(50).optional(),
      read_only: z.boolean().optional(),
      allowed_paths: z.array(z.string().trim().max(500)).max(50).optional(),
    })
    .passthrough(),
  provider_preference: z.string().trim().max(60).optional(),
  model_preference: z.string().trim().max(120).optional(),
  work_dir: z.string().trim().max(500).optional(),
  notification_policy: z.object({ mode: z.string().max(30) }).passthrough().optional(),
  verification_policy: z.object({ mode: z.string().max(30) }).passthrough().optional(),
  auto_activate: z.boolean().default(true),
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
