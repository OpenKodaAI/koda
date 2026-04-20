import { z } from "zod";

/**
 * Mirrors backend validation in `koda/control_plane/manager.py::_validate_general_payload`.
 *
 * The backend is the source of truth. This schema is a fast-fail layer that
 * surfaces structural errors to the user without a network round-trip. When
 * the two layers disagree, backend wins — always re-check the server response.
 *
 * Only rules that are *context-free* (no server state needed) live here. Rules
 * like "provider exists in the managed catalog" are left to the backend.
 */

export type SettingsSectionId =
  | "general"
  | "models"
  | "integrations"
  | "intelligence"
  | "variables";

export type SystemSettingsFieldError = {
  field: string;
  code: string;
  message: string;
};

const ALLOWED_AUTONOMY_TIERS = ["t0", "t1", "t2"] as const;
const ALLOWED_PROVENANCE_POLICIES = ["strict", "standard"] as const;
const ALLOWED_VARIABLE_TYPES = ["text", "secret"] as const;
const ALLOWED_VARIABLE_SCOPES = ["system_only", "agent_grant"] as const;
const ENV_KEY_REGEX = /^[A-Z][A-Z0-9_]*$/;

const optionalNumber = z
  .union([z.number(), z.string(), z.null()])
  .optional()
  .transform((value, ctx) => {
    if (value === undefined || value === null || value === "") return undefined;
    const parsed = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(parsed)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "invalid_type" });
      return z.NEVER;
    }
    return parsed;
  });

const accountSchema = z
  .object({
    rate_limit_per_minute: z
      .union([z.number(), z.string(), z.null()])
      .optional()
      .transform((value, ctx) => {
        if (value === undefined || value === null || value === "") return undefined;
        const parsed = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(parsed) || !Number.isInteger(parsed)) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, message: "invalid_type" });
          return z.NEVER;
        }
        if (parsed < 1) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, message: "min_value" });
          return z.NEVER;
        }
        return parsed;
      }),
  })
  .passthrough();

const functionalDefaultSelectionSchema = z
  .object({
    provider_id: z.string().optional(),
    model_id: z.string().optional(),
  })
  .passthrough();

const modelsSchema = z
  .object({
    max_budget_usd: optionalNumber,
    max_total_budget_usd: optionalNumber,
    providers_enabled: z.array(z.string()).optional(),
    default_provider: z.string().optional(),
    functional_defaults: z.record(z.string(), functionalDefaultSelectionSchema).optional(),
  })
  .passthrough()
  .superRefine((value, ctx) => {
    if (
      typeof value.max_budget_usd === "number" &&
      value.max_budget_usd <= 0
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["max_budget_usd"],
        message: "must_be_positive",
      });
    }
    if (
      typeof value.max_total_budget_usd === "number" &&
      value.max_total_budget_usd < 0
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["max_total_budget_usd"],
        message: "must_be_non_negative",
      });
    }
    if (
      typeof value.max_budget_usd === "number" &&
      typeof value.max_total_budget_usd === "number" &&
      value.max_total_budget_usd < value.max_budget_usd
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["max_total_budget_usd"],
        message: "must_gte_max_budget",
      });
    }
    const enabled = value.providers_enabled;
    if (Array.isArray(enabled) && typeof value.default_provider === "string") {
      const normalized = value.default_provider.trim().toLowerCase();
      if (normalized && !enabled.includes(normalized)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["default_provider"],
          message: "must_be_enabled",
        });
      }
    }
    if (Array.isArray(enabled) && value.functional_defaults) {
      for (const [fnId, selection] of Object.entries(value.functional_defaults)) {
        const pid = (selection?.provider_id ?? "").toString().trim().toLowerCase();
        if (pid && !enabled.includes(pid)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["functional_defaults", fnId, "provider_id"],
            message: "must_be_enabled",
          });
        }
      }
    }
  });

const autonomyPolicySchema = z
  .object({
    default_autonomy_tier: z
      .string()
      .optional()
      .refine(
        (v) => !v || ALLOWED_AUTONOMY_TIERS.includes(v.toLowerCase() as (typeof ALLOWED_AUTONOMY_TIERS)[number]),
        { message: "invalid_enum" },
      ),
  })
  .passthrough();

const profileShape = z
  .object({ id: z.string().optional() })
  .passthrough();

const knowledgePolicySchema = z
  .object({
    profile: profileShape.optional(),
    profile_id: z.string().optional(),
    provenance_policy: z
      .string()
      .optional()
      .refine(
        (v) => !v || ALLOWED_PROVENANCE_POLICIES.includes(v.toLowerCase() as (typeof ALLOWED_PROVENANCE_POLICIES)[number]),
        { message: "invalid_enum" },
      ),
  })
  .passthrough();

const memoryPolicySchema = z
  .object({
    profile: profileShape.optional(),
    profile_id: z.string().optional(),
  })
  .passthrough();

const memoryAndKnowledgeSchema = z
  .object({
    autonomy_policy: autonomyPolicySchema.optional(),
    memory_policy: memoryPolicySchema.optional(),
    knowledge_policy: knowledgePolicySchema.optional(),
  })
  .passthrough();

const variableSchema = z
  .object({
    key: z.string(),
    type: z.string().optional(),
    scope: z.string().optional(),
  })
  .passthrough()
  .superRefine((value, ctx) => {
    const key = (value.key ?? "").toString().trim();
    if (!key) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["key"], message: "required" });
    } else if (!ENV_KEY_REGEX.test(key)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["key"],
        message: "invalid_format",
      });
    }
    const type = (value.type ?? "text").toString().toLowerCase();
    if (!ALLOWED_VARIABLE_TYPES.includes(type as (typeof ALLOWED_VARIABLE_TYPES)[number])) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["type"], message: "invalid_enum" });
    }
    const scope = (value.scope ?? "system_only").toString().toLowerCase();
    if (!ALLOWED_VARIABLE_SCOPES.includes(scope as (typeof ALLOWED_VARIABLE_SCOPES)[number])) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["scope"], message: "invalid_enum" });
    }
  });

export const generalSystemSettingsPayloadSchema = z
  .object({
    account: accountSchema.optional(),
    models: modelsSchema.optional(),
    resources: z.record(z.string(), z.unknown()).optional(),
    memory_and_knowledge: memoryAndKnowledgeSchema.optional(),
    variables: z.array(variableSchema).optional(),
  })
  .passthrough();

export type GeneralSystemSettingsPayload = z.infer<typeof generalSystemSettingsPayloadSchema>;

/** Human-readable, PT-BR messages keyed by `code` from the backend/zod. */
const ERROR_MESSAGES: Record<string, string> = {
  invalid_type: "Valor deve ser numérico.",
  min_value: "Valor deve ser ao menos 1.",
  must_be_positive: "Valor deve ser maior que zero.",
  must_be_non_negative: "Valor não pode ser negativo.",
  must_gte_max_budget: "Orçamento total deve ser maior ou igual ao orçamento por tarefa.",
  must_be_enabled: "Provider selecionado não está habilitado.",
  invalid_enum: "Valor fora da lista permitida.",
  unknown_provider: "Provider desconhecido.",
  unknown_profile: "Perfil desconhecido.",
  required: "Campo obrigatório.",
  invalid_format: "Formato inválido.",
};

export function humanizeCode(code: string, fallback?: string): string {
  return ERROR_MESSAGES[code] ?? fallback ?? code;
}

/** Maps a dotted field path to the owning section. */
export function sectionForField(field: string): SettingsSectionId {
  if (field.startsWith("account.")) return "general";
  if (field.startsWith("models.")) return "models";
  if (field.startsWith("resources.") || field.startsWith("integrations.")) return "integrations";
  if (field.startsWith("memory_and_knowledge.")) return "intelligence";
  if (field.startsWith("variables")) return "variables";
  return "general";
}

/**
 * Run the zod schema and transform zod errors into the same structured shape
 * the backend uses: `{ field, code, message }`.
 */
export function validatePayloadClientSide(
  payload: unknown,
): SystemSettingsFieldError[] {
  const result = generalSystemSettingsPayloadSchema.safeParse(payload);
  if (result.success) return [];
  return result.error.issues.map((issue) => {
    const field = issue.path.map(String).join(".");
    const code = issue.message || "invalid";
    return { field, code, message: humanizeCode(code) };
  });
}

/** Groups a flat error list into per-section buckets for UI rendering. */
export function groupErrorsBySection(
  errors: SystemSettingsFieldError[],
): Record<SettingsSectionId, SystemSettingsFieldError[]> {
  const initial: Record<SettingsSectionId, SystemSettingsFieldError[]> = {
    general: [],
    models: [],
    integrations: [],
    intelligence: [],
    variables: [],
  };
  for (const err of errors) {
    initial[sectionForField(err.field)].push(err);
  }
  return initial;
}
