import "server-only";

import { CONTROL_PLANE_CACHE_TAGS, getControlPlaneFetchConfig, type ControlPlaneFetchTier } from "@/lib/control-plane-cache";
import { getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";

const CONTROL_PLANE_BASE_URL =
  process.env.CONTROL_PLANE_BASE_URL || "http://127.0.0.1:8090";

export class ControlPlaneRequestError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ControlPlaneRequestError";
    this.status = status;
  }
}

export type ControlPlaneBotOrganization = {
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_color?: string | null;
  squad_id?: string | null;
  squad_name?: string | null;
  squad_color?: string | null;
};

export type ControlPlaneWorkspaceSquad = {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  color: string;
  bot_count: number;
  created_at: string;
  updated_at: string;
};

export type ControlPlaneWorkspace = {
  id: string;
  name: string;
  description: string;
  color: string;
  bot_count: number;
  squads: ControlPlaneWorkspaceSquad[];
  virtual_buckets: {
    no_squad: {
      id: null;
      label: string;
      bot_count: number;
    };
  };
  created_at: string;
  updated_at: string;
};

export type ControlPlaneWorkspaceTree = {
  items: ControlPlaneWorkspace[];
  virtual_buckets: {
    no_workspace: {
      id: null;
      label: string;
      bot_count: number;
    };
  };
  total_bot_count: number;
};

export type ControlPlaneBotSummary = {
  id: string;
  display_name: string;
  status: string;
  appearance: {
    label?: string;
    color?: string;
    color_rgb?: string;
  };
  storage_namespace: string;
  runtime_endpoint: Record<string, unknown>;
  metadata: Record<string, unknown>;
  organization: ControlPlaneBotOrganization;
  default_model_provider_id?: string;
  default_model_provider_label?: string;
  default_model_id?: string;
  default_model_label?: string;
  applied_version?: number | null;
  desired_version?: number | null;
};

export type ControlPlaneEnvEntry = {
  key: string;
  value: string;
};

export type ControlPlaneSecretSummary = {
  id?: number;
  scope: string;
  secret_key: string;
  preview: string;
  grantable_to_agents?: boolean;
  grantable_to_bots?: boolean;
  usage_scope?: string;
  updated_at?: string;
};

export type ControlPlaneSystemSettingsSection = Record<
  string,
  string | number | boolean | string[] | null | undefined
>;

export type ControlPlaneSystemSettings = {
  version: number;
  general: ControlPlaneSystemSettingsSection;
  providers: ControlPlaneSystemSettingsSection;
  tools: ControlPlaneSystemSettingsSection;
  integrations: ControlPlaneSystemSettingsSection;
  memory: ControlPlaneSystemSettingsSection;
  knowledge: ControlPlaneSystemSettingsSection;
  runtime: ControlPlaneSystemSettingsSection;
  scheduler: ControlPlaneSystemSettingsSection;
  shared_variables: ControlPlaneEnvEntry[];
  additional_env_vars: ControlPlaneEnvEntry[];
  global_secrets: ControlPlaneSecretSummary[];
};

export type GeneralSystemSettingsValueSource =
  | "custom"
  | "env"
  | "system_default";

export type GeneralSystemSettingsVariable = {
  key: string;
  type: "text" | "secret";
  scope: "system_only" | "bot_grant";
  description: string;
  value: string;
  preview: string;
  value_present: boolean;
  clear?: boolean;
};

export type GeneralSystemSettingsCredentialField = {
  key: string;
  label: string;
  input_type: string;
  storage: "env" | "secret";
  required: boolean;
  value?: string;
  preview?: string;
  value_present?: boolean;
  usage_scope?: "system_only" | "bot_grant";
  clear?: boolean;
};

export type GeneralSystemSettingsProviderConnection = {
  provider_id: string;
  title: string;
  auth_mode: "api_key" | "subscription_login" | "local";
  configured: boolean;
  verified: boolean;
  account_label: string;
  plan_label: string;
  last_verified_at: string;
  last_error: string;
  project_id: string;
  command_present: boolean;
  supports_api_key: boolean;
  supports_subscription_login: boolean;
  supports_local_connection?: boolean;
  supported_auth_modes: string[];
  login_flow_kind?: string | null;
  requires_project_id: boolean;
  api_key_present: boolean;
  api_key_preview?: string;
  base_url?: string;
  connection_status: "not_configured" | "configured" | "verified" | "error" | string;
};

export type ElevenLabsVoiceOption = {
  voice_id: string;
  name: string;
  gender: string;
  accent: string;
  category: string;
  preview_url: string;
  languages: Array<{
    code: string;
    label: string;
  }>;
};

export type ElevenLabsVoiceCatalog = {
  items: ElevenLabsVoiceOption[];
  available_languages: Array<{
    code: string;
    label: string;
  }>;
  selected_language: string;
  cached: boolean;
  provider_connected: boolean;
};

export type KokoroVoiceOption = {
  voice_id: string;
  name: string;
  gender: string;
  language_id: string;
  language_label: string;
  lang_code: string;
  tts_lang: string;
  download_url: string;
  sha256_prefix: string;
  downloaded: boolean;
  local_path: string;
};

export type KokoroVoiceCatalog = {
  items: KokoroVoiceOption[];
  available_languages: Array<{
    id: string;
    label: string;
  }>;
  selected_language: string;
  default_language: string;
  default_voice: string;
  default_voice_label?: string;
  downloaded_voice_ids: string[];
  provider_connected: boolean;
};

export type ProviderDownloadJob = {
  id: string;
  provider_id: string;
  asset_id: string;
  status: "pending" | "running" | "completed" | "error" | "cancelled" | string;
  downloaded_bytes: number;
  total_bytes: number;
  progress_percent: number;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  voice_id?: string;
  voice_name?: string;
  language_id?: string;
  language_label?: string;
  local_path?: string;
  message?: string;
  last_error?: string;
};

export type OllamaModelOption = {
  model_id: string;
  name: string;
  family: string;
  parameter_size: string;
  quantization_level: string;
  format: string;
  modified_at: string;
  size: number;
};

export type OllamaModelCatalog = {
  items: OllamaModelOption[];
  cached: boolean;
  provider_connected: boolean;
  base_url: string;
  auth_mode: "api_key" | "local" | string;
};

export type ProviderLoginSession = {
  session_id: string;
  provider_id: string;
  auth_mode: "api_key" | "subscription_login" | "local";
  status: string;
  command: string;
  auth_url: string;
  user_code: string;
  message: string;
  instructions: string;
  output_preview: string;
  last_error: string;
  completed_at?: string;
  created_at?: string;
  updated_at?: string;
};

export type ControlPlaneMemoryPolicy = Record<string, unknown>;
export type ControlPlaneKnowledgePolicy = Record<string, unknown>;
export type ControlPlaneAutonomyPolicy = Record<string, unknown>;

export type GeneralSystemSettings = {
  version: number;
  values: {
    account: {
      owner_name: string;
      owner_email: string;
      owner_github: string;
      default_work_dir: string;
      project_dirs: string[];
      scheduler_default_timezone: string;
      rate_limit_per_minute?: number | null;
    };
    models: {
      providers_enabled: string[];
      default_provider: string;
      fallback_order: string[];
      usage_profile: string;
      max_budget_usd?: number | null;
      max_total_budget_usd?: number | null;
      elevenlabs_default_language: string;
      elevenlabs_default_voice: string;
      elevenlabs_default_voice_label: string;
      kokoro_default_language: string;
      kokoro_default_voice: string;
      kokoro_default_voice_label: string;
      functional_defaults: Record<
        string,
        {
          provider_id: string;
          model_id: string;
          provider_title?: string;
          model_label?: string;
        }
      >;
    };
    resources: {
      global_tools: string[];
      integrations: Record<string, boolean>;
    };
    memory_and_knowledge: {
      memory_enabled: boolean;
      memory_profile: string;
      procedural_enabled: boolean;
      proactive_enabled: boolean;
      knowledge_enabled: boolean;
      knowledge_profile: string;
      provenance_policy: string;
      promotion_mode: string;
      memory_policy: ControlPlaneMemoryPolicy;
      knowledge_policy: ControlPlaneKnowledgePolicy;
      autonomy_policy: ControlPlaneAutonomyPolicy;
    };
    variables: GeneralSystemSettingsVariable[];
    integration_credentials: Record<
      string,
      {
        title: string;
        description: string;
        fields: GeneralSystemSettingsCredentialField[];
      }
    >;
    provider_connections: Record<string, GeneralSystemSettingsProviderConnection>;
  };
  source_badges: Record<string, GeneralSystemSettingsValueSource>;
  catalogs: {
    providers: Array<Record<string, unknown>>;
    model_functions: Array<{
      id: string;
      title: string;
      description: string;
    }>;
    functional_model_catalog: Record<
      string,
      Array<{
        provider_id: string;
        provider_title: string;
        provider_vendor?: string;
        provider_category?: string;
        provider_enabled?: boolean;
        command_present?: boolean;
        model_id: string;
        title: string;
        description?: string;
        status?: string;
      }>
    >;
    global_tools: Array<Record<string, unknown>>;
    usage_profiles: Array<Record<string, unknown>>;
    memory_profiles: Array<Record<string, unknown>>;
    knowledge_profiles: Array<Record<string, unknown>>;
    provenance_policies: Array<Record<string, unknown>>;
    knowledge_layers: Array<Record<string, unknown>>;
    approval_modes: Array<Record<string, unknown>>;
    autonomy_tiers: Array<Record<string, unknown>>;
  };
  review: {
    warnings: string[];
    hidden_sections: string[];
  };
};

export type ControlPlanePromptPreviewSegment = {
  segment_id: string;
  runtime_tag?: string;
  scope?: string;
  category?: string;
  drop_policy?: string;
  token_estimate?: number;
  final_token_estimate?: number;
  char_count?: number;
  metadata?: Record<string, unknown>;
};

export type ControlPlanePromptBudget = {
  target_tokens?: number;
  compiled_tokens?: number;
  available_tokens?: number;
  overflow_tokens?: number;
  within_budget?: boolean;
  reserved_output_tokens?: number;
  max_system_prompt_tokens?: number;
  hard_floor_tokens?: number;
  discretionary_tokens?: number;
  gate_reason?: string;
  dropped_segments?: string[];
  truncated_segments?: string[];
  ordered_categories?: string[];
  final_segment_order?: string[];
  category_token_caps?: Record<string, number>;
  included_segments?: Array<Record<string, unknown>>;
};

export type ControlPlanePromptPreview = {
  bot_id?: string | null;
  preview_scope?: string;
  provider?: string;
  model?: string;
  compiled_tokens?: number;
  compiled_prompt?: string;
  segment_order?: string[];
  final_segment_order?: string[];
  runtime_hard_floor_order?: string[];
  runtime_discretionary_category_order?: string[];
  runtime_unmodeled_segments?: Array<Record<string, unknown>>;
  ordered_categories?: string[];
  dropped_segments?: string[];
  segments?: ControlPlanePromptPreviewSegment[];
  budget?: ControlPlanePromptBudget;
  runtime_alignment?: Record<string, unknown>;
};

export type ControlPlaneCompiledPrompt = {
  bot_id: string;
  compiled_prompt: string;
  documents: Record<string, string>;
  document_sources?: Record<string, Record<string, unknown>>;
  sections_present?: string[];
  document_lengths?: Record<string, number>;
  prompt_preview?: ControlPlanePromptPreview;
  agent_contract_prompt_preview?: ControlPlanePromptPreview;
  bot_contract_prompt_preview?: ControlPlanePromptPreview;
  runtime_prompt_preview?: ControlPlanePromptPreview;
};

export type ControlPlaneValidation = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  compiled_prompt: string;
  documents: Record<string, string>;
  document_sources?: Record<string, Record<string, unknown>>;
  document_lengths?: Record<string, number>;
  sections_present?: string[];
  tool_policy_summary?: {
    requested_tool_ids?: string[];
    allowed_tool_ids?: string[];
    count?: number;
    categories?: Record<string, number>;
  };
  provider_catalog?: Record<string, unknown>;
  provider_errors?: string[];
  provenance_warnings?: string[];
  resource_warnings?: string[];
  resource_errors?: string[];
  feature_flags?: Record<string, boolean>;
  prompt_preview?: ControlPlanePromptPreview;
  agent_contract_prompt_preview?: ControlPlanePromptPreview;
  bot_contract_prompt_preview?: ControlPlanePromptPreview;
  runtime_prompt_preview?: ControlPlanePromptPreview;
};

export type ControlPlaneCoreTools = {
  items: Array<Record<string, unknown>>;
  governance: Record<string, unknown>;
};

export type ControlPlaneCoreProviders = {
  default_provider?: string;
  enabled_providers?: string[];
  fallback_order?: string[];
  governance?: Record<string, unknown>;
  providers: Record<string, Record<string, unknown>>;
};

export type ControlPlaneCorePolicies = Record<string, unknown>;

export type ControlPlaneCoreCapabilities = {
  providers: Array<Record<string, unknown>>;
};

export type ControlPlaneBot = ControlPlaneBotSummary & {
  sections: Record<string, Record<string, unknown>>;
  documents: Record<string, string>;
  knowledge_assets: Array<Record<string, unknown>>;
  knowledge_candidates?: Array<Record<string, unknown>>;
  templates: Array<Record<string, unknown>>;
  skills: Array<Record<string, unknown>>;
  runbooks?: Array<Record<string, unknown>>;
  secrets: Array<Record<string, unknown>>;
  draft_snapshot: Record<string, unknown>;
  published_snapshot: Record<string, unknown> | null;
  versions: Array<Record<string, unknown>>;
  agent_spec: Record<string, unknown>;
  compiled_prompt: string;
  validation: ControlPlaneValidation;
};

export type ControlPlaneRuntimeAccess = {
  bot_id: string;
  applied_version?: number | null;
  desired_version?: number | null;
  selected_version?: number | null;
  health_url: string;
  runtime_base_url: string;
  runtime_token?: string | null;
  runtime_request_token?: string | null;
  runtime_request_expires_at?: string | null;
  runtime_request_capability?: string | null;
  access_scope?: Record<string, unknown> | null;
  access_scope_token?: string | null;
  access_scope_expires_at?: string | null;
  runtime_token_present: boolean;
};

export type ControlPlaneServerRuntimeAccess = ControlPlaneRuntimeAccess;

const PREVIEW_ONLY_KEYS = new Set([
  "preview",
  "api_key_preview",
  "output_preview",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sanitizeControlPlaneNode(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeControlPlaneNode(item));
  }

  if (!isRecord(value)) {
    return value;
  }

  const secretTypedRecord =
    value.type === "secret" ||
    value.storage === "secret" ||
    "secret_key" in value;

  const result: Record<string, unknown> = {};

  for (const [key, rawChild] of Object.entries(value)) {
    if (
      key === "runtime_token" ||
      key === "runtime_request_token" ||
      key === "access_scope_token"
    ) {
      result[key] = null;
      continue;
    }

    if (PREVIEW_ONLY_KEYS.has(key)) {
      result[key] = "";
      continue;
    }

    if (secretTypedRecord && key === "value") {
      result[key] = "";
      continue;
    }

    result[key] = sanitizeControlPlaneNode(rawChild);
  }

  return result;
}

export function sanitizeControlPlanePayload<T>(
  pathname: string,
  payload: T,
): T {
  if (!pathname.startsWith("/api/control-plane/") || payload == null) {
    return payload;
  }

  return sanitizeControlPlaneNode(payload) as T;
}

type ControlPlaneFetchOptions = {
  tier?: ControlPlaneFetchTier;
  tags?: string[];
};

function buildUrl(pathname: string) {
  return new URL(
    pathname,
    CONTROL_PLANE_BASE_URL.endsWith("/")
      ? CONTROL_PLANE_BASE_URL
      : `${CONTROL_PLANE_BASE_URL}/`,
  );
}

export async function controlPlaneFetch(
  pathname: string,
  init: RequestInit = {},
  options: ControlPlaneFetchOptions = {},
) {
  const headers = new Headers(init.headers);

  const operatorToken = await getWebOperatorTokenFromCookie();
  if (!operatorToken) {
    throw new ControlPlaneRequestError("Operator session is required", 401);
  }

  if (operatorToken) {
    headers.set("Authorization", `Bearer ${operatorToken}`);
  }
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const fetchConfig = getControlPlaneFetchConfig(
      options.tier ?? "live",
      options.tags,
    );
    return await fetch(buildUrl(pathname), {
      ...init,
      ...fetchConfig,
      headers,
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Control plane endpoint is unavailable";
    throw new ControlPlaneRequestError(message, 503);
  }
}

export async function controlPlaneFetchJson<T>(
  pathname: string,
  init: RequestInit = {},
  options: ControlPlaneFetchOptions = {},
) {
  const response = await controlPlaneFetch(pathname, init, options);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Control plane request failed with status ${response.status}`;
    throw new ControlPlaneRequestError(message, response.status);
  }

  return sanitizeControlPlanePayload(pathname, payload as T);
}

export async function getControlPlaneBots() {
  const payload = await controlPlaneFetchJson<{
    items: ControlPlaneBotSummary[];
  }>("/api/control-plane/agents", {}, {
    tier: "catalog",
    tags: [CONTROL_PLANE_CACHE_TAGS.catalog],
  });
  return payload.items;
}

export async function getControlPlaneWorkspaces() {
  return controlPlaneFetchJson<ControlPlaneWorkspaceTree>(
    "/api/control-plane/workspaces",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.catalog, CONTROL_PLANE_CACHE_TAGS.workspaces],
    },
  );
}

export async function getControlPlaneBot(botId: string) {
  return controlPlaneFetchJson<ControlPlaneBot>(
    `/api/control-plane/agents/${botId}`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.bot(botId)],
    },
  );
}

export async function getControlPlaneCompiledPrompt(botId: string) {
  return controlPlaneFetchJson<ControlPlaneCompiledPrompt>(
    `/api/control-plane/agents/${botId}/compiled-prompt`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.bot(botId)],
    },
  );
}

export async function getControlPlaneGlobalDefaults() {
  return controlPlaneFetchJson<{
    sections: Record<string, Record<string, unknown>>;
    version: number;
  }>("/api/control-plane/global-defaults", {}, {
    tier: "catalog",
    tags: [CONTROL_PLANE_CACHE_TAGS.system],
  });
}

export async function getControlPlaneSystemSettings() {
  return controlPlaneFetchJson<ControlPlaneSystemSettings>(
    "/api/control-plane/system-settings",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.system],
    },
  );
}

export async function getGeneralSystemSettings() {
  return controlPlaneFetchJson<GeneralSystemSettings>(
    "/api/control-plane/system-settings/general",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.systemGeneral],
    },
  );
}

export async function getControlPlaneRuntimeAccess(botId: string) {
  return controlPlaneFetchJson<ControlPlaneRuntimeAccess>(
    `/api/control-plane/agents/${botId}/runtime-access`,
    {},
    {
      tier: "live",
    },
  );
}

type ControlPlaneRuntimeAccessRequest = {
  capability?: "read" | "mutate" | "attach";
  includeSensitive?: boolean;
};

export async function getServerControlPlaneRuntimeAccess(
  botId: string,
  options: ControlPlaneRuntimeAccessRequest = {},
) {
  const searchParams = new URLSearchParams();
  if (options.capability) {
    searchParams.set("capability", options.capability);
  }
  if (options.includeSensitive) {
    searchParams.set("include_sensitive", "true");
  }
  const suffix = searchParams.size ? `?${searchParams.toString()}` : "";
  const response = await controlPlaneFetch(
    `/api/control-plane/agents/${botId}/runtime-access${suffix}`,
    {},
    {
      tier: "live",
    },
  );
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Control plane request failed with status ${response.status}`;
    throw new ControlPlaneRequestError(message, response.status);
  }

  return payload as ControlPlaneServerRuntimeAccess;
}

export async function getControlPlaneCoreTools() {
  return controlPlaneFetchJson<ControlPlaneCoreTools>(
    "/api/control-plane/core/tools",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}

export async function getControlPlaneCoreProviders() {
  return controlPlaneFetchJson<ControlPlaneCoreProviders>(
    "/api/control-plane/core/providers",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}

export async function getControlPlaneCorePolicies() {
  return controlPlaneFetchJson<ControlPlaneCorePolicies>(
    "/api/control-plane/core/policies",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}

export async function getControlPlaneCoreCapabilities() {
  return controlPlaneFetchJson<ControlPlaneCoreCapabilities>(
    "/api/control-plane/core/capabilities",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}
