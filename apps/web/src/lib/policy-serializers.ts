/* -------------------------------------------------------------------------- */
/*  Policy Serializers — structured form ↔ canonical AgentSpec JSON           */
/* -------------------------------------------------------------------------- */

import type { ControlPlaneCoreProviders } from "@/lib/control-plane";

function safeParseJson(json: string): Record<string, unknown> {
  const trimmed = json.trim();
  if (!trimmed || trimmed === "{}") return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return {};
  } catch {
    return {};
  }
}

function extractKnown<T extends Record<string, unknown>>(
  obj: Record<string, unknown>,
  keys: string[],
): { known: Partial<T>; extra: Record<string, unknown> } {
  const known: Record<string, unknown> = {};
  const extra: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (keys.includes(key)) {
      known[key] = value;
    } else {
      extra[key] = value;
    }
  }
  return { known: known as Partial<T>, extra };
}

function mergeBack(
  structured: Record<string, unknown>,
  extra: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...extra };
  for (const [key, value] of Object.entries(structured)) {
    if (key === "_extra") continue;
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    if (
      typeof value === "object" &&
      !Array.isArray(value) &&
      value !== null &&
      Object.keys(value).length === 0
    ) {
      continue;
    }
    result[key] = value;
  }
  return result;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asBool(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;
  return fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).map((item) => item.trim()).filter(Boolean);
}

function asObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asStringMap(value: unknown): Record<string, string> {
  const obj = asObject(value);
  return Object.fromEntries(
    Object.entries(obj)
      .map(([key, item]) => [key, asString(item)])
      .filter(([, item]) => item),
  );
}

function asProviderModels(value: unknown): Record<string, string[]> {
  const obj = asObject(value);
  return Object.fromEntries(
    Object.entries(obj)
      .map(([provider, models]) => [provider, asStringArray(models)])
      .filter(([, models]) => models.length > 0),
  );
}

function asTierModels(
  value: unknown,
): Record<string, { small?: string; medium?: string; large?: string }> {
  const obj = asObject(value);
  return Object.fromEntries(
    Object.entries(obj)
      .map(([provider, tiers]) => {
        const tierObj = asObject(tiers);
        const normalized = {
          small: asString(tierObj.small),
          medium: asString(tierObj.medium),
          large: asString(tierObj.large),
        };
        return [
          provider,
          Object.fromEntries(
            Object.entries(normalized).filter(([, item]) => item),
          ),
        ];
      })
      .filter(([, tiers]) => Object.keys(tiers).length > 0),
  );
}

/* -------------------------------------------------------------------------- */
/*  Mission Profile                                                           */
/* -------------------------------------------------------------------------- */

export interface MissionProfileData {
  mission: string;
  role: string;
  audience: string;
  primary_outcomes: string[];
  kpis: string[];
  responsibility_limits: string[];
  _extra: Record<string, unknown>;
}

const MISSION_PROFILE_KEYS = [
  "mission",
  "role",
  "audience",
  "primary_outcomes",
  "kpis",
  "responsibility_limits",
];

export function parseMissionProfile(json: string): MissionProfileData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, MISSION_PROFILE_KEYS);
  return {
    mission: asString(known.mission),
    role: asString(known.role),
    audience: asString(known.audience),
    primary_outcomes: asStringArray(known.primary_outcomes),
    kpis: asStringArray(known.kpis),
    responsibility_limits: asStringArray(known.responsibility_limits),
    _extra: extra,
  };
}

export function serializeMissionProfile(data: MissionProfileData): string {
  return JSON.stringify(
    mergeBack(
      {
        mission: data.mission,
        role: data.role,
        audience: data.audience,
        primary_outcomes: data.primary_outcomes,
        kpis: data.kpis,
        responsibility_limits: data.responsibility_limits,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Interaction Style                                                         */
/* -------------------------------------------------------------------------- */

export interface InteractionStyleData {
  tone: string;
  persona: string;
  values: string[];
  collaboration_style: string;
  writing_style: string;
  escalation_style: string;
  _extra: Record<string, unknown>;
}

const INTERACTION_STYLE_KEYS = [
  "tone",
  "persona",
  "values",
  "collaboration_style",
  "writing_style",
  "escalation_style",
];

export function parseInteractionStyle(json: string): InteractionStyleData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, INTERACTION_STYLE_KEYS);
  return {
    tone: asString(known.tone, "profissional"),
    persona: asString(known.persona),
    values: asStringArray(known.values),
    collaboration_style: asString(known.collaboration_style, "colaborativo"),
    writing_style: asString(known.writing_style, "claro e direto"),
    escalation_style: asString(known.escalation_style, "escalar com contexto"),
    _extra: extra,
  };
}

export function serializeInteractionStyle(data: InteractionStyleData): string {
  return JSON.stringify(
    mergeBack(
      {
        tone: data.tone,
        persona: data.persona,
        values: data.values,
        collaboration_style: data.collaboration_style,
        writing_style: data.writing_style,
        escalation_style: data.escalation_style,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Operating Instructions                                                    */
/* -------------------------------------------------------------------------- */

export interface OperatingInstructionsData {
  default_workflow: string[];
  execution_heuristics: string[];
  success_criteria: string[];
  handoff_expectations: string[];
  _extra: Record<string, unknown>;
}

const OPERATING_INSTRUCTIONS_KEYS = [
  "default_workflow",
  "execution_heuristics",
  "success_criteria",
  "handoff_expectations",
];

export function parseOperatingInstructions(
  json: string,
): OperatingInstructionsData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, OPERATING_INSTRUCTIONS_KEYS);
  return {
    default_workflow: asStringArray(known.default_workflow),
    execution_heuristics: asStringArray(known.execution_heuristics),
    success_criteria: asStringArray(known.success_criteria),
    handoff_expectations: asStringArray(known.handoff_expectations),
    _extra: extra,
  };
}

export function serializeOperatingInstructions(
  data: OperatingInstructionsData,
): string {
  return JSON.stringify(
    mergeBack(
      {
        default_workflow: data.default_workflow,
        execution_heuristics: data.execution_heuristics,
        success_criteria: data.success_criteria,
        handoff_expectations: data.handoff_expectations,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Hard Rules                                                                */
/* -------------------------------------------------------------------------- */

export interface HardRulesData {
  non_negotiables: string[];
  forbidden_actions: string[];
  approval_requirements: string[];
  security_rules: string[];
  _extra: Record<string, unknown>;
}

const HARD_RULES_KEYS = [
  "non_negotiables",
  "forbidden_actions",
  "approval_requirements",
  "security_rules",
];

export function parseHardRules(json: string): HardRulesData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, HARD_RULES_KEYS);
  return {
    non_negotiables: asStringArray(known.non_negotiables),
    forbidden_actions: asStringArray(known.forbidden_actions),
    approval_requirements: asStringArray(known.approval_requirements),
    security_rules: asStringArray(known.security_rules),
    _extra: extra,
  };
}

export function serializeHardRules(data: HardRulesData): string {
  return JSON.stringify(
    mergeBack(
      {
        non_negotiables: data.non_negotiables,
        forbidden_actions: data.forbidden_actions,
        approval_requirements: data.approval_requirements,
        security_rules: data.security_rules,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Response Policy                                                           */
/* -------------------------------------------------------------------------- */

export interface ResponsePolicyData {
  language: string;
  format: string;
  citation_policy: string;
  source_policy: string;
  conciseness: string;
  quality_bar: string;
  _extra: Record<string, unknown>;
}

const RESPONSE_POLICY_KEYS = [
  "language",
  "format",
  "citation_policy",
  "source_policy",
  "conciseness",
  "quality_bar",
];

export function parseResponsePolicy(json: string): ResponsePolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, RESPONSE_POLICY_KEYS);
  return {
    language: asString(known.language, "pt-BR"),
    format: asString(known.format, "markdown"),
    citation_policy: asString(known.citation_policy, "cite when grounded"),
    source_policy: asString(known.source_policy, "prefer grounded sources"),
    conciseness: asString(known.conciseness, "balanced"),
    quality_bar: asString(known.quality_bar, "professional"),
    _extra: extra,
  };
}

export function serializeResponsePolicy(data: ResponsePolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        language: data.language,
        format: data.format,
        citation_policy: data.citation_policy,
        source_policy: data.source_policy,
        conciseness: data.conciseness,
        quality_bar: data.quality_bar,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Autonomy Policy                                                           */
/* -------------------------------------------------------------------------- */

export interface AutonomyPolicyData {
  default_approval_mode: string;
  default_autonomy_tier: string;
  task_overrides: Record<string, unknown>;
  _extra: Record<string, unknown>;
}

const AUTONOMY_POLICY_KEYS = [
  "default_approval_mode",
  "default_autonomy_tier",
  "task_overrides",
];

export function parseAutonomyPolicy(json: string): AutonomyPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, AUTONOMY_POLICY_KEYS);
  return {
    default_approval_mode: asString(known.default_approval_mode, "guarded"),
    default_autonomy_tier: asString(known.default_autonomy_tier, "t1"),
    task_overrides: asObject(known.task_overrides),
    _extra: extra,
  };
}

export function serializeAutonomyPolicy(data: AutonomyPolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        default_approval_mode: data.default_approval_mode,
        default_autonomy_tier: data.default_autonomy_tier,
        task_overrides: data.task_overrides,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Model Policy                                                              */
/* -------------------------------------------------------------------------- */

export interface ModelPolicyData {
  allowed_providers: string[];
  default_provider: string;
  fallback_order: string[];
  available_models_by_provider: Record<string, string[]>;
  default_models: Record<string, string>;
  tier_models: Record<string, { small?: string; medium?: string; large?: string }>;
  functional_defaults: Record<string, { provider_id: string; model_id: string }>;
  max_budget_usd: number | null;
  max_total_budget_usd: number | null;
  _extra: Record<string, unknown>;
}

const MODEL_POLICY_KEYS = [
  "allowed_providers",
  "default_provider",
  "fallback_order",
  "available_models_by_provider",
  "default_models",
  "tier_models",
  "functional_defaults",
  "max_budget_usd",
  "max_total_budget_usd",
];

function asFunctionalDefaults(value: unknown): Record<string, { provider_id: string; model_id: string }> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, { provider_id: string; model_id: string }> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const providerId = asString((raw as Record<string, unknown>).provider_id);
    const modelId = asString((raw as Record<string, unknown>).model_id);
    if (!providerId || !modelId) continue;
    result[key] = { provider_id: providerId, model_id: modelId };
  }
  return result;
}

export function parseModelPolicy(json: string): ModelPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, MODEL_POLICY_KEYS);
  return {
    allowed_providers: asStringArray(known.allowed_providers),
    default_provider: asString(known.default_provider),
    fallback_order: asStringArray(known.fallback_order),
    available_models_by_provider: asProviderModels(
      known.available_models_by_provider,
    ),
    default_models: asStringMap(known.default_models),
    tier_models: asTierModels(known.tier_models),
    functional_defaults: asFunctionalDefaults(known.functional_defaults),
    max_budget_usd:
      known.max_budget_usd === undefined || known.max_budget_usd === null
        ? null
        : asNumber(known.max_budget_usd),
    max_total_budget_usd:
      known.max_total_budget_usd === undefined ||
      known.max_total_budget_usd === null
        ? null
        : asNumber(known.max_total_budget_usd),
    _extra: extra,
  };
}

export function serializeModelPolicy(data: ModelPolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        allowed_providers: data.allowed_providers,
        default_provider: data.default_provider,
        fallback_order: data.fallback_order,
        available_models_by_provider: data.available_models_by_provider,
        default_models: data.default_models,
        tier_models: data.tier_models,
        functional_defaults: data.functional_defaults,
        max_budget_usd: data.max_budget_usd,
        max_total_budget_usd: data.max_total_budget_usd,
      },
      data._extra,
    ),
    null,
    2,
  );
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

export function normalizeModelPolicyForCore(
  data: ModelPolicyData,
  coreProviders: ControlPlaneCoreProviders,
): ModelPolicyData {
  const providerEntries = coreProviders.providers ?? {};
  const enabledProviders = Array.isArray(coreProviders.enabled_providers)
    ? coreProviders.enabled_providers.map(String).filter(Boolean)
    : Object.entries(providerEntries)
        .filter(([, payload]) => Boolean(payload?.enabled))
        .map(([provider]) => provider);

  const generalProviders = enabledProviders.filter(
    (provider) =>
      String(providerEntries[provider]?.category || "general") === "general",
  );
  const allowedProviders = uniqueStrings(
    data.allowed_providers.filter((provider) => generalProviders.includes(provider)),
  );
  const effectiveAllowedProviders =
    allowedProviders.length > 0 ? allowedProviders : generalProviders;
  const defaultProvider = effectiveAllowedProviders.includes(data.default_provider)
    ? data.default_provider
    : effectiveAllowedProviders[0] || "";

  const availableModelsByProvider = Object.fromEntries(
    effectiveAllowedProviders.map((provider) => {
      const requested = data.available_models_by_provider[provider];
      const fallback = Array.isArray(providerEntries[provider]?.available_models)
        ? providerEntries[provider].available_models.map(String).filter(Boolean)
        : [];
      const models = requested && requested.length > 0 ? requested : fallback;
      return [provider, models];
    }).filter(([, models]) => Array.isArray(models) && models.length > 0),
  );

  const defaultModels = Object.fromEntries(
    effectiveAllowedProviders.map((provider) => {
      const requested = data.default_models[provider];
      const firstAvailable = availableModelsByProvider[provider]?.[0] || "";
      const model = requested || firstAvailable;
      return [provider, model];
    }).filter(([, model]) => Boolean(model)),
  );

  const tierModels = Object.fromEntries(
    effectiveAllowedProviders.map((provider) => {
      const current = data.tier_models[provider] || {};
      const fallback = defaultModels[provider] || availableModelsByProvider[provider]?.[0] || "";
      const tiers = {
        ...current,
        medium: current.medium || fallback,
      };
      return [
        provider,
        Object.fromEntries(
          Object.entries(tiers).filter(([, model]) => Boolean(model)),
        ),
      ];
    }).filter(([, tiers]) => Object.keys(tiers).length > 0),
  );

  const fallbackOrder = defaultProvider
    ? uniqueStrings([
        defaultProvider,
        ...data.fallback_order.filter((provider) =>
          effectiveAllowedProviders.includes(provider),
        ),
        ...effectiveAllowedProviders,
      ])
    : uniqueStrings(
        data.fallback_order.filter((provider) =>
          effectiveAllowedProviders.includes(provider),
        ),
      );

  return {
    ...data,
    allowed_providers: effectiveAllowedProviders,
    default_provider: defaultProvider,
    fallback_order: fallbackOrder,
    available_models_by_provider: availableModelsByProvider,
    default_models: defaultModels,
    tier_models: tierModels,
  };
}

/* -------------------------------------------------------------------------- */
/*  Tool Policy                                                               */
/* -------------------------------------------------------------------------- */

export interface ToolPolicyData {
  allowed_tool_ids: string[];
  _extra: Record<string, unknown>;
}

const TOOL_POLICY_KEYS = ["allowed_tool_ids"];

export function parseToolPolicy(json: string): ToolPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, TOOL_POLICY_KEYS);
  return {
    allowed_tool_ids: asStringArray(known.allowed_tool_ids),
    _extra: extra,
  };
}

export function serializeToolPolicy(data: ToolPolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        allowed_tool_ids: data.allowed_tool_ids,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Resource Access Policy                                                    */
/* -------------------------------------------------------------------------- */

export interface ResourceAccessPolicyData {
  allowed_global_secret_keys: string[];
  allowed_shared_env_keys: string[];
  local_env: Record<string, string>;
  _extra: Record<string, unknown>;
}

const RESOURCE_ACCESS_POLICY_KEYS = [
  "allowed_global_secret_keys",
  "allowed_shared_env_keys",
  "local_env",
];

export function parseResourceAccessPolicy(json: string): ResourceAccessPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, RESOURCE_ACCESS_POLICY_KEYS);
  return {
    allowed_global_secret_keys: asStringArray(known.allowed_global_secret_keys),
    allowed_shared_env_keys: asStringArray(known.allowed_shared_env_keys),
    local_env: asStringMap(known.local_env),
    _extra: extra,
  };
}

export function serializeResourceAccessPolicy(data: ResourceAccessPolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        allowed_global_secret_keys: data.allowed_global_secret_keys,
        allowed_shared_env_keys: data.allowed_shared_env_keys,
        local_env: data.local_env,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Memory Policy                                                             */
/* -------------------------------------------------------------------------- */

export interface MemoryPolicyData {
  enabled: boolean;
  max_recall: number;
  recall_threshold: number;
  recall_timeout: number;
  max_context_tokens: number;
  recency_half_life_days: number;
  max_extraction_items: number;
  extraction_provider: string;
  extraction_model: string;
  proactive_enabled: boolean;
  procedural_enabled: boolean;
  procedural_max_recall: number;
  similarity_dedup_threshold: number;
  max_per_user: number;
  maintenance_enabled: boolean;
  digest_enabled: boolean;
  risk_posture: string;
  memory_density_target: string;
  preferred_layers: string[];
  forbidden_layers_for_actions: string[];
  focus_domains: string[];
  max_items_per_turn: number;
  observed_pattern_requires_review: boolean;
  minimum_verified_successes: number;
  _extra: Record<string, unknown>;
}

const MEMORY_POLICY_KEYS = [
  "enabled",
  "max_recall",
  "recall_threshold",
  "recall_timeout",
  "max_context_tokens",
  "recency_half_life_days",
  "max_extraction_items",
  "extraction_provider",
  "extraction_model",
  "proactive_enabled",
  "procedural_enabled",
  "procedural_max_recall",
  "similarity_dedup_threshold",
  "max_per_user",
  "maintenance_enabled",
  "digest_enabled",
  "profile",
];

export function parseMemoryPolicy(json: string): MemoryPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, MEMORY_POLICY_KEYS);
  const profile = asObject(known.profile);
  const promotionPolicy = asObject(profile.promotion_policy);
  return {
    enabled: asBool(known.enabled, true),
    max_recall: asNumber(known.max_recall, 25),
    recall_threshold: asNumber(known.recall_threshold, 0.25),
    recall_timeout: asNumber(known.recall_timeout, 3),
    max_context_tokens: asNumber(known.max_context_tokens, 3500),
    recency_half_life_days: asNumber(known.recency_half_life_days, 120),
    max_extraction_items: asNumber(known.max_extraction_items, 15),
    extraction_provider: asString(known.extraction_provider),
    extraction_model: asString(known.extraction_model),
    proactive_enabled: asBool(known.proactive_enabled, true),
    procedural_enabled: asBool(known.procedural_enabled, true),
    procedural_max_recall: asNumber(known.procedural_max_recall, 4),
    similarity_dedup_threshold: asNumber(known.similarity_dedup_threshold, 0.92),
    max_per_user: asNumber(known.max_per_user, 2000),
    maintenance_enabled: asBool(known.maintenance_enabled, true),
    digest_enabled: asBool(known.digest_enabled, true),
    risk_posture: asString(profile.risk_posture, "balanced"),
    memory_density_target: asString(profile.memory_density_target, "focused"),
    preferred_layers: asStringArray(profile.preferred_layers),
    forbidden_layers_for_actions: asStringArray(
      profile.forbidden_layers_for_actions,
    ),
    focus_domains: asStringArray(profile.focus_domains),
    max_items_per_turn: asNumber(profile.max_items_per_turn, 6),
    observed_pattern_requires_review: asBool(
      promotionPolicy.observed_pattern_requires_review,
      true,
    ),
    minimum_verified_successes: asNumber(
      promotionPolicy.minimum_verified_successes,
      3,
    ),
    _extra: extra,
  };
}

export function serializeMemoryPolicy(data: MemoryPolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        enabled: data.enabled,
        max_recall: data.max_recall,
        recall_threshold: data.recall_threshold,
        recall_timeout: data.recall_timeout,
        max_context_tokens: data.max_context_tokens,
        recency_half_life_days: data.recency_half_life_days,
        max_extraction_items: data.max_extraction_items,
        extraction_provider: data.extraction_provider,
        extraction_model: data.extraction_model,
        proactive_enabled: data.proactive_enabled,
        procedural_enabled: data.procedural_enabled,
        procedural_max_recall: data.procedural_max_recall,
        similarity_dedup_threshold: data.similarity_dedup_threshold,
        max_per_user: data.max_per_user,
        maintenance_enabled: data.maintenance_enabled,
        digest_enabled: data.digest_enabled,
        profile: mergeBack(
          {
            risk_posture: data.risk_posture,
            memory_density_target: data.memory_density_target,
            preferred_layers: data.preferred_layers,
            forbidden_layers_for_actions: data.forbidden_layers_for_actions,
            focus_domains: data.focus_domains,
            max_items_per_turn: data.max_items_per_turn,
            promotion_policy: mergeBack(
              {
                observed_pattern_requires_review:
                  data.observed_pattern_requires_review,
                minimum_verified_successes: data.minimum_verified_successes,
              },
              {},
            ),
          },
          {},
        ),
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Knowledge Policy                                                          */
/* -------------------------------------------------------------------------- */

export interface KnowledgePolicyData {
  enabled: boolean;
  allowed_layers: string[];
  max_results: number;
  recall_threshold: number;
  recall_timeout: number;
  context_max_tokens: number;
  workspace_max_files: number;
  source_globs: string[];
  workspace_source_globs: string[];
  max_observed_patterns: number;
  max_source_age_days: number;
  require_owner_provenance: boolean;
  require_freshness_provenance: boolean;
  promotion_mode: string;
  _extra: Record<string, unknown>;
}

const KNOWLEDGE_POLICY_KEYS = [
  "enabled",
  "allowed_layers",
  "max_results",
  "recall_threshold",
  "recall_timeout",
  "context_max_tokens",
  "workspace_max_files",
  "source_globs",
  "workspace_source_globs",
  "max_observed_patterns",
  "max_source_age_days",
  "require_owner_provenance",
  "require_freshness_provenance",
  "promotion_mode",
];

export function parseKnowledgePolicy(json: string): KnowledgePolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, KNOWLEDGE_POLICY_KEYS);
  return {
    enabled: asBool(known.enabled, true),
    allowed_layers: asStringArray(known.allowed_layers),
    max_results: asNumber(known.max_results, 6),
    recall_threshold: asNumber(known.recall_threshold, 0.35),
    recall_timeout: asNumber(known.recall_timeout, 2),
    context_max_tokens: asNumber(known.context_max_tokens, 2200),
    workspace_max_files: asNumber(known.workspace_max_files, 24),
    source_globs: asStringArray(known.source_globs),
    workspace_source_globs: asStringArray(known.workspace_source_globs),
    max_observed_patterns: asNumber(known.max_observed_patterns, 3),
    max_source_age_days: asNumber(known.max_source_age_days, 3650),
    require_owner_provenance: asBool(
      known.require_owner_provenance,
      false,
    ),
    require_freshness_provenance: asBool(
      known.require_freshness_provenance,
      false,
    ),
    promotion_mode: asString(known.promotion_mode, "review_queue"),
    _extra: extra,
  };
}

export function serializeKnowledgePolicy(data: KnowledgePolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        enabled: data.enabled,
        allowed_layers: data.allowed_layers,
        max_results: data.max_results,
        recall_threshold: data.recall_threshold,
        recall_timeout: data.recall_timeout,
        context_max_tokens: data.context_max_tokens,
        workspace_max_files: data.workspace_max_files,
        source_globs: data.source_globs,
        workspace_source_globs: data.workspace_source_globs,
        max_observed_patterns: data.max_observed_patterns,
        max_source_age_days: data.max_source_age_days,
        require_owner_provenance: data.require_owner_provenance,
        require_freshness_provenance: data.require_freshness_provenance,
        promotion_mode: data.promotion_mode,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Voice Policy                                                              */
/* -------------------------------------------------------------------------- */

export interface VoicePolicyData {
  mode: string;
  style: string;
  duration_target: string;
  tts_notes: string;
  _extra: Record<string, unknown>;
}

const VOICE_POLICY_KEYS = ["mode", "style", "duration_target", "tts_notes"];

export function parseVoicePolicy(json: string): VoicePolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, VOICE_POLICY_KEYS);
  return {
    mode: asString(known.mode, "disabled"),
    style: asString(known.style),
    duration_target: asString(known.duration_target),
    tts_notes: asString(known.tts_notes),
    _extra: extra,
  };
}

export function serializeVoicePolicy(data: VoicePolicyData): string {
  return JSON.stringify(
    mergeBack(
      {
        mode: data.mode,
        style: data.style,
        duration_target: data.duration_target,
        tts_notes: data.tts_notes,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Image Analysis Policy                                                     */
/* -------------------------------------------------------------------------- */

export interface ImageAnalysisPolicyData {
  fallback_behavior: string;
  analysis_priorities: string[];
  safety_notes: string[];
  _extra: Record<string, unknown>;
}

const IMAGE_ANALYSIS_POLICY_KEYS = [
  "fallback_behavior",
  "analysis_priorities",
  "safety_notes",
];

export function parseImageAnalysisPolicy(
  json: string,
): ImageAnalysisPolicyData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, IMAGE_ANALYSIS_POLICY_KEYS);
  return {
    fallback_behavior: asString(known.fallback_behavior, "describe"),
    analysis_priorities: asStringArray(known.analysis_priorities),
    safety_notes: asStringArray(known.safety_notes),
    _extra: extra,
  };
}

export function serializeImageAnalysisPolicy(
  data: ImageAnalysisPolicyData,
): string {
  return JSON.stringify(
    mergeBack(
      {
        fallback_behavior: data.fallback_behavior,
        analysis_priorities: data.analysis_priorities,
        safety_notes: data.safety_notes,
      },
      data._extra,
    ),
    null,
    2,
  );
}

/* -------------------------------------------------------------------------- */
/*  Memory Extraction Schema                                                  */
/* -------------------------------------------------------------------------- */

export interface MemoryExtractionSchemaData {
  template: string;
  _extra: Record<string, unknown>;
}

const MEMORY_EXTRACTION_SCHEMA_KEYS = ["template"];

export function parseMemoryExtractionSchema(
  json: string,
): MemoryExtractionSchemaData {
  const obj = safeParseJson(json);
  const { known, extra } = extractKnown(obj, MEMORY_EXTRACTION_SCHEMA_KEYS);
  return {
    template: asString(known.template),
    _extra: extra,
  };
}

export function serializeMemoryExtractionSchema(
  data: MemoryExtractionSchemaData,
): string {
  return JSON.stringify(
    mergeBack(
      { template: data.template },
      data._extra,
    ),
    null,
    2,
  );
}
