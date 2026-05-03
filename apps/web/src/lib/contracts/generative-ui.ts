import { z } from "zod";
import { safeContent, safeText } from "@/lib/contracts/sanitizers";

/* ------------------------------------------------------------------ */
/*  Generative UI block contracts                                      */
/*                                                                    */
/*  Schema rules:                                                      */
/*  - Versioning is additive: new fields use .optional(); breaking     */
/*    changes ship as a new schema name (e.g. uiCardV2).               */
/*  - Strings are bounded (sanitizers). Records are bounded by .max(). */
/*  - state="streaming" allows partial payloads at the consumer; the   */
/*    full schema is enforced only when state="complete".              */
/* ------------------------------------------------------------------ */

const blockId = z.string().trim().min(1).max(120);
const blockBase = z.object({
  id: blockId,
  version: z.literal(1),
  state: z.enum(["streaming", "complete", "error"]).default("complete"),
});

const blockActionLink = z.object({
  kind: z.literal("link"),
  href: z.string().trim().url().max(2000),
});

const blockActionSubmit = z.object({
  kind: z.literal("submit"),
});

const blockActionEmit = z.object({
  kind: z.literal("emit"),
  value: z.string().trim().max(240),
});

const blockAction = z.discriminatedUnion("kind", [
  blockActionLink,
  blockActionSubmit,
  blockActionEmit,
]);

/* ----- ui_card --------------------------------------------------- */

const uiCardFooterAction = z.object({
  id: z.string().trim().min(1).max(64),
  label: safeText(48),
  tone: z.enum(["primary", "accent", "ghost"]).default("ghost"),
  action: blockAction,
});

export const uiCardBlockSchema = blockBase.extend({
  block_type: z.literal("ui_card"),
  payload: z.object({
    eyebrow: safeText(48).optional(),
    title: safeText(120),
    body: safeContent(2000).optional(),
    media: z
      .object({
        src: z.string().trim().url().max(2000),
        alt: safeText(120),
      })
      .optional(),
    footer_actions: z.array(uiCardFooterAction).max(3).optional(),
  }),
});

/* ----- ui_table -------------------------------------------------- */

const uiTableColumn = z.object({
  key: z.string().trim().min(1).max(64),
  label: safeText(64),
  align: z.enum(["start", "end", "center"]).default("start"),
  sortable: z.boolean().default(false),
  format: z
    .enum(["text", "number", "date", "duration", "cost", "status"])
    .default("text"),
});

const uiTableCell = z.union([z.string().max(500), z.number(), z.boolean(), z.null()]);

export const uiTableBlockSchema = blockBase.extend({
  block_type: z.literal("ui_table"),
  payload: z.object({
    title: safeText(120).optional(),
    columns: z.array(uiTableColumn).min(1).max(12),
    rows: z.array(z.record(z.string(), uiTableCell)).max(200),
    empty_label: safeText(80).optional(),
  }),
});

/* ----- ui_chart -------------------------------------------------- */

export const uiChartBlockSchema = blockBase.extend({
  block_type: z.literal("ui_chart"),
  payload: z.object({
    title: safeText(120).optional(),
    kind: z.enum(["line", "bar", "area"]),
    x_key: z.string().trim().min(1).max(64),
    y_keys: z.array(z.string().trim().min(1).max(64)).min(1).max(4),
    data: z.array(z.record(z.string(), z.union([z.string().max(120), z.number()]))).max(200),
    unit: z.enum(["count", "cost_usd", "ms", "percent"]).default("count"),
  }),
});

/* ----- ui_form --------------------------------------------------- */

const uiFormFieldText = z.object({
  kind: z.literal("text"),
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  placeholder: safeText(120).optional(),
  required: z.boolean().default(false),
  max: z.number().int().positive().max(2000).default(280),
});

const uiFormFieldTextarea = z.object({
  kind: z.literal("textarea"),
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  placeholder: safeText(120).optional(),
  required: z.boolean().default(false),
  max: z.number().int().positive().max(8000).default(1000),
});

const uiFormFieldNumber = z.object({
  kind: z.literal("number"),
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  required: z.boolean().default(false),
  min: z.number().optional(),
  max: z.number().optional(),
  step: z.number().positive().optional(),
});

const uiFormFieldSelect = z.object({
  kind: z.literal("select"),
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  required: z.boolean().default(false),
  options: z
    .array(
      z.object({
        value: z.string().trim().min(1).max(120),
        label: safeText(120),
      }),
    )
    .min(1)
    .max(20),
});

const uiFormFieldToggle = z.object({
  kind: z.literal("toggle"),
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  default: z.boolean().default(false),
});

export const uiFormFieldSchema = z.discriminatedUnion("kind", [
  uiFormFieldText,
  uiFormFieldTextarea,
  uiFormFieldNumber,
  uiFormFieldSelect,
  uiFormFieldToggle,
]);

export type UiFormField = z.infer<typeof uiFormFieldSchema>;

export const uiFormBlockSchema = blockBase.extend({
  block_type: z.literal("ui_form"),
  payload: z.object({
    title: safeText(120).optional(),
    description: safeContent(800).optional(),
    fields: z.array(uiFormFieldSchema).min(1).max(8),
    submit_label: safeText(32).default("Submit"),
  }),
});

/* ----- ui_callout ------------------------------------------------ */

export const uiCalloutBlockSchema = blockBase.extend({
  block_type: z.literal("ui_callout"),
  payload: z.object({
    tone: z.enum(["neutral", "info", "success", "warning", "danger"]),
    title: safeText(80).optional(),
    body: safeContent(800),
    action: z
      .object({
        id: z.string().trim().min(1).max(64),
        label: safeText(40),
      })
      .optional(),
  }),
});

/* ----- ui_choice ------------------------------------------------- */

const uiChoiceOption = z.object({
  id: z.string().trim().min(1).max(64),
  label: safeText(80),
  description: safeText(200).optional(),
});

export const uiChoiceBlockSchema = blockBase.extend({
  block_type: z.literal("ui_choice"),
  payload: z.object({
    prompt: safeText(240),
    multi: z.boolean().default(false),
    options: z.array(uiChoiceOption).min(2).max(8),
    submit_label: safeText(32).default("Submit"),
  }),
});

/* ----- ui_steps -------------------------------------------------- */

const uiStepStatus = z.enum(["pending", "running", "done", "failed", "skipped"]);

const uiStepItem = z.object({
  id: z.string().trim().min(1).max(64),
  label: safeText(120),
  status: uiStepStatus,
  detail: safeText(240).optional(),
});

export const uiStepsBlockSchema = blockBase.extend({
  block_type: z.literal("ui_steps"),
  payload: z.object({
    title: safeText(120).optional(),
    items: z.array(uiStepItem).min(1).max(20),
  }),
});

/* ----- discriminated union --------------------------------------- */

export const generativeBlockSchema = z.discriminatedUnion("block_type", [
  uiCardBlockSchema,
  uiTableBlockSchema,
  uiChartBlockSchema,
  uiFormBlockSchema,
  uiCalloutBlockSchema,
  uiChoiceBlockSchema,
  uiStepsBlockSchema,
]);

export type GenerativeBlock = z.infer<typeof generativeBlockSchema>;
export type GenerativeBlockType = GenerativeBlock["block_type"];

/**
 * Lenient parse — returns null when the block isn't recognized or fails
 * validation. Consumers handle null by rendering UnsupportedBlock.
 */
export function parseGenerativeBlock(raw: unknown): GenerativeBlock | null {
  const result = generativeBlockSchema.safeParse(raw);
  return result.success ? result.data : null;
}

/**
 * Pre-validate just the block_type + state so the renderer can choose between
 * Skeleton (state="streaming") and full validation (state="complete") without
 * exploding on partial payloads.
 */
const blockEnvelopeSchema = z.object({
  block_type: z.string().min(1).max(64),
  state: z.enum(["streaming", "complete", "error"]).default("complete"),
});

export type GenerativeBlockEnvelope = z.infer<typeof blockEnvelopeSchema>;

export function parseGenerativeBlockEnvelope(
  raw: unknown,
): GenerativeBlockEnvelope | null {
  if (!raw || typeof raw !== "object") return null;
  const result = blockEnvelopeSchema.safeParse(raw);
  return result.success ? result.data : null;
}
