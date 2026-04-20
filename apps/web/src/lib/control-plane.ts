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

export type ControlPlaneAgentOrganization = {
  workspace_id?: string | null;
  workspace_name?: string | null;
  squad_id?: string | null;
  squad_name?: string | null;
};

/* -------------------------------------------------------------------------- */
/*  Workspace / Squad spec types — hierarchical prompt governance              */
/* -------------------------------------------------------------------------- */

export type WorkspaceSpec = Record<string, never>;
export type SquadSpec = Record<string, never>;

export interface ScopePromptDocuments {
  system_prompt_md?: string;
}

/* -------------------------------------------------------------------------- */
/*  Workspace / Squad entity types                                             */
/* -------------------------------------------------------------------------- */

export type ControlPlaneWorkspaceSquad = {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  bot_count: number;
  spec?: SquadSpec;
  documents?: ScopePromptDocuments;
  created_at: string;
  updated_at: string;
};

export type ControlPlaneWorkspace = {
  id: string;
  name: string;
  description: string;
  bot_count: number;
  spec?: WorkspaceSpec;
  documents?: ScopePromptDocuments;
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

export type ControlPlaneAgentSummary = {
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
  organization: ControlPlaneAgentOrganization;
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
  connection_managed?: boolean;
  show_in_settings?: boolean;
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
export type ControlPlaneExecutionPolicy = {
  version?: number;
  source?: string;
  defaults?: Record<string, unknown>;
  rules?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};
export type ControlPlaneExecutionPolicyCatalogAction = {
  action_id?: string;
  tool_id?: string;
  integration_id?: string;
  title?: string;
  description?: string;
  transport?: string;
  access_level?: string;
  risk_class?: string;
  effect_tags?: string[];
  resource_method?: string;
  server_key?: string;
  default_decision?: string;
  default_reason_code?: string;
  preview_required_default?: boolean;
  approval_scope_default?: string;
  [key: string]: unknown;
};
export type ControlPlaneExecutionPolicyCatalog = {
  version: number;
  decision_values: string[];
  effect_tags: string[];
  selector_keys: string[];
  tool_ids?: string[];
  actions?: ControlPlaneExecutionPolicyCatalogAction[];
  approval_scope_templates?: Array<Record<string, unknown>>;
  selector_groups?: Array<Record<string, unknown>>;
  core_tools?: Array<Record<string, unknown>>;
  core_integrations?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};
export type ControlPlaneExecutionPolicyPayload = {
  agent_id: string;
  policy: ControlPlaneExecutionPolicy;
  source: string;
  catalog: ControlPlaneExecutionPolicyCatalog;
  legacy: {
    tool_policy: Record<string, unknown>;
    autonomy_policy: Record<string, unknown>;
    resource_access_policy: Record<string, unknown>;
  };
};
export type ControlPlaneExecutionPolicyEvaluation = {
  agent_id: string;
  policy: ControlPlaneExecutionPolicy;
  catalog: ControlPlaneExecutionPolicyCatalog;
  action: Record<string, unknown>;
  evaluation: {
    decision?: string;
    reason_code?: string;
    rule_id?: string | null;
    matched_selector?: Record<string, unknown> | null;
    audit_payload?: Record<string, unknown>;
    approval_scope?: Record<string, unknown> | null;
    preview_text?: string | null;
    policy?: ControlPlaneExecutionPolicy;
    [key: string]: unknown;
  };
};

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
      time_format?: string;
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
    provider_connections: Record<string, GeneralSystemSettingsProviderConnection>;
  };
  source_badges: Record<string, GeneralSystemSettingsValueSource>;
  catalogs: {
    providers: GeneralSystemSettingsCatalogProvider[];
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

export type ControlPlaneAgent = ControlPlaneAgentSummary & {
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

/* -------------------------------------------------------------------------- */
/*  MCP types                                                                  */
/* -------------------------------------------------------------------------- */

export type McpToolPolicy = "auto" | "always_allow" | "always_ask" | "blocked";

export type McpToolPolicyEntry = {
  tool_name: string;
  policy: McpToolPolicy;
};

export type McpDiscoveredTool = {
  name: string;
  description: string;
  annotations?: {
    title?: string;
    read_only_hint?: boolean;
    destructive_hint?: boolean;
    idempotent_hint?: boolean;
    [key: string]: unknown;
  };
  input_schema?: Record<string, unknown>;
};

export type McpEnvSchemaField = {
  key: string;
  label: string;
  required: boolean;
  input_type?: string;
};

/* -------------------------------------------------------------------------- */
/*  ConnectionProfile — declarative per-integration connection contract        */
/* -------------------------------------------------------------------------- */

export type ConnectionStrategy =
  | "none"
  | "api_key"
  | "connection_string"
  | "dual_token"
  | "local_path"
  | "local_app"
  | "oauth_only"
  | "oauth_preferred";

export type RuntimeConstraintKey =
  | "allowed_domains"
  | "allowed_paths"
  | "allowed_db_envs"
  | "allow_private_network"
  | "read_only_mode";

export type ConnectionField = {
  key: string;
  label: string;
  required?: boolean;
  input_type?: "password" | "text" | "textarea" | "switch";
  help?: string | null;
};

export type ConnectionProfile = {
  strategy: ConnectionStrategy;
  oauth_provider?: string | null;
  oauth_scopes?: string[];
  fields?: ConnectionField[];
  scope_fields?: ConnectionField[];
  read_only_toggle?: ConnectionField | null;
  path_argument?: ConnectionField | null;
  local_app_name?: string | null;
  local_app_detection_hint?: string | null;
};

export type CatalogExtension = {
  connection_profile?: ConnectionProfile | null;
  runtime_constraints?: RuntimeConstraintKey[];
  default_tool_policy?: "auto" | "always_ask";
};

export type McpServerCatalogEntry = {
  server_key: string;
  display_name: string;
  description: string;
  transport_type: "stdio" | "http_sse";
  transport_kind?: string;
  command?: string[];
  command_json?: string | null;
  url?: string | null;
  remote_url?: string | null;
  category: string;
  enabled: boolean;
  env_schema_json?: string | null;
  env_schema?: McpEnvSchemaField[];
  headers_schema?: McpEnvSchemaField[];
  headers_schema_json?: string | null;
  tool_discovery_mode?: string | null;
  official_support_level?: string | null;
  auth_strategy?: string | null;
  oauth_enabled?: boolean;
  oauth_mode?: string | null;
  oauth_metadata_url?: string | null;
  vendor_notes?: string | null;
  default_policy?: McpToolPolicy | null;
  auth_capabilities?: Record<string, unknown> | null;
  documentation_url?: string | null;
  logo_key?: string | null;
  metadata?: Record<string, unknown>;
  metadata_json?: string | null;
  connection_profile?: ConnectionProfile | null;
  runtime_constraints?: RuntimeConstraintKey[];
  created_at?: string;
  updated_at?: string;
};

export type McpAgentConnection = {
  server_key: string;
  agent_id?: string;
  enabled: boolean;
  transport_override?: string | null;
  command_override?: string[] | null;
  command_override_json?: string | null;
  url_override?: string | null;
  cached_tools_json?: string;
  cached_tools_at?: string | null;
  last_connected_at?: string | null;
  last_error?: string;
  env_values?: Record<string, string>;
  auth_method?: "manual" | "oauth";
  metadata?: Record<string, unknown>;
  tool_count?: number;
  created_at?: string;
  updated_at?: string;
};

export type McpOAuthStatus = {
  connected: boolean;
  expires_at: string | null;
  provider_account_id?: string | null;
  account_label: string | null;
  last_error: string | null;
  auth_method: "manual" | "oauth";
};

export type ControlPlaneConnectionCatalogEntry = {
  connection_key: string;
  kind: "core" | "mcp";
  integration_key: string;
  display_name: string;
  description: string;
  category: string;
  transport_kind?: string | null;
  auth_capabilities?: Record<string, unknown> | null;
  auth_strategy_default?: string | null;
  official_support_level?: string | null;
  oauth_mode?: string | null;
  remote_url?: string | null;
  vendor_notes?: string | null;
  default_policy?: McpToolPolicy | null;
  env_schema?: McpEnvSchemaField[];
  headers_schema?: McpEnvSchemaField[];
  documentation_url?: string | null;
  logo_key?: string | null;
  metadata?: Record<string, unknown> | null;
  enabled?: boolean;
  connection_profile?: ConnectionProfile | null;
  runtime_constraints?: RuntimeConstraintKey[];
};

export type ControlPlaneAgentConnection = {
  connection_key: string;
  kind: "core" | "mcp";
  integration_key: string;
  status: string;
  transport_kind?: string | null;
  auth_strategy?: string | null;
  auth_method?: string | null;
  official_support_level?: string | null;
  source_origin?: "agent_binding" | "imported_default" | "local_session" | "system_default" | string | null;
  account_label?: string | null;
  provider_account_id?: string | null;
  expires_at?: string | null;
  last_verified_at?: string | null;
  last_error?: string | null;
  tool_count?: number;
  connected: boolean;
  metadata?: Record<string, unknown> | null;
  enabled?: boolean;
  agent_id?: string;
  fields?: Array<Record<string, unknown>>;
  server_key?: string;
  command_override?: string[] | null;
  command_override_json?: string | null;
  transport_override?: string | null;
  url_override?: string | null;
  env_values?: Record<string, string>;
  cached_tools_json?: string | null;
  cached_tools_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type ControlPlaneConnectionTools = {
  connection_key: string;
  kind: "core" | "mcp";
  integration_key: string;
  tools: McpDiscoveredTool[];
  policies: Record<string, McpToolPolicy>;
  summary: {
    total: number;
    read_only: number;
    write: number;
    destructive: number;
  };
  last_discovered_at: string | null;
  diff: {
    added: string[];
    removed: string[];
    changed: string[];
  };
};

/* -------------------------------------------------------------------------- */
/*  Core integration type                                                      */
/* -------------------------------------------------------------------------- */

export type ControlPlaneCoreIntegration = {
  id: string;
  integration_id?: string;
  title: string;
  description?: string;
  enabled?: boolean;
  configured?: boolean;
  category?: string;
  transport?: string;
  auth_modes?: string[];
  auth_mode?: string;
  connection_status?: string;
  health_probe?: string;
  supports_persistence?: boolean;
  connection?: ControlPlaneCoreIntegrationConnection;
  connection_profile?: ConnectionProfile | null;
  runtime_constraints?: RuntimeConstraintKey[];
  [key: string]: unknown;
};

export type ControlPlaneCoreIntegrations = {
  items: ControlPlaneCoreIntegration[];
  governance: Record<string, unknown>;
};

export type ControlPlaneCoreIntegrationConnection = {
  connection_key?: string;
  kind?: "core";
  integration_key?: string;
  integration_id: string;
  title: string;
  description?: string;
  transport?: string;
  auth_modes?: string[];
  auth_mode?: string;
  auth_method?: string;
  auth_strategy?: string;
  source_origin?: "agent_binding" | "imported_default" | "local_session" | "system_default" | string | null;
  configured: boolean;
  verified: boolean;
  account_label?: string;
  provider_account_id?: string | null;
  expires_at?: string | null;
  last_verified_at?: string;
  last_error?: string;
  checked_via?: string;
  auth_expired?: boolean;
  metadata?: Record<string, unknown>;
  fields?: Array<Record<string, unknown>>;
  health_probe?: string;
  supports_persistence?: boolean;
  connection_status?: string;
  status?: string;
  connected?: boolean;
  enabled?: boolean;
  tool_count?: number;
};

export type GeneralSystemSettingsCatalogProvider = {
  id: string;
  title: string;
  vendor?: string;
  category?: string;
  enabled_by_default?: boolean;
  command_present?: boolean;
  available_models?: Array<Record<string, unknown>>;
  default_model?: string;
  supported_auth_modes?: string[];
  supports_api_key?: boolean;
  supports_subscription_login?: boolean;
  supports_local_connection?: boolean;
  login_flow_kind?: string;
  requires_project_id?: boolean;
  connection_managed?: boolean;
  show_in_settings?: boolean;
  connection_status?: string;
  functional_models?: Array<Record<string, unknown>>;
};

/* -------------------------------------------------------------------------- */
/*  Onboarding status type                                                     */
/* -------------------------------------------------------------------------- */

export type ControlPlaneOnboardingStatus = {
  has_owner?: boolean;
  bootstrap_required?: boolean;
  auth_mode?: string;
  session_required?: boolean;
  recovery_available?: boolean;
  control_plane: {
    ready: boolean;
    [key: string]: unknown;
  };
  storage: {
    database: {
      ready: boolean;
      reason?: string;
      [key: string]: unknown;
    };
    object_storage: {
      ready: boolean;
      reason?: string;
      [key: string]: unknown;
    };
  };
  providers: Array<{
    provider_id: string;
    title: string;
    supported_auth_modes: string[];
    configured: boolean;
    verified: boolean;
    connection_status: Record<string, unknown>;
    [key: string]: unknown;
  }>;
  agents: Array<{
    agent_id: string;
    display_name?: string;
    telegram_token_configured: boolean;
    [key: string]: unknown;
  }>;
  system: {
    owner_name: string;
    owner_email: string;
    owner_github: string;
    default_provider: string;
    allowed_user_ids: Array<string | number>;
    [key: string]: unknown;
  };
  steps: {
    provider_configured: boolean;
    access_configured: boolean;
    agent_ready: boolean;
    storage_ready: boolean;
    onboarding_complete: boolean;
    [key: string]: unknown;
  };
  openapi_url?: string;
  setup_url?: string;
};

export type ControlPlaneAuthStatus = {
  authenticated: boolean;
  has_owner: boolean;
  bootstrap_required: boolean;
  auth_mode: string;
  session_required: boolean;
  recovery_available: boolean;
  onboarding_complete?: boolean;
  loopback_trust_enabled?: boolean;
  bootstrap_file_path?: string;
  session_subject?: string | null;
  operator?: {
    id?: string | null;
    username?: string | null;
    email?: string | null;
    display_name?: string | null;
  } | null;
};

const PREVIEW_ONLY_KEYS = new Set([
  "preview",
  "api_key_preview",
  "output_preview",
]);

const STRIP_KEYS = new Set([
  "encrypted_value",
  "access_token_encrypted",
  "refresh_token_encrypted",
  "client_secret_encrypted",
  "env_values_json",
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

    if (STRIP_KEYS.has(key)) {
      continue; // completely omit from result
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
  // Strip query params from the base URL so only the request path is sent downstream.
  const cleanBase = CONTROL_PLANE_BASE_URL.split("?")[0];
  return new URL(
    pathname,
    cleanBase.endsWith("/") ? cleanBase : `${cleanBase}/`,
  );
}

export async function controlPlaneFetch(
  pathname: string,
  init: RequestInit = {},
  options: ControlPlaneFetchOptions = {},
) {
  const headers = new Headers(init.headers);

  const operatorToken = await getWebOperatorTokenFromCookie();
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

export async function getControlPlaneAgents() {
  const payload = await controlPlaneFetchJson<{
    items: ControlPlaneAgentSummary[];
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

export async function getControlPlaneAgent(agentId: string) {
  return controlPlaneFetchJson<ControlPlaneAgent>(
    `/api/control-plane/agents/${agentId}`,
    {},
    {
      tier: "live",
    },
  );
}

export async function getControlPlaneCompiledPrompt(agentId: string) {
  return controlPlaneFetchJson<ControlPlaneCompiledPrompt>(
    `/api/control-plane/agents/${agentId}/compiled-prompt`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.agent(agentId)],
    },
  );
}

export async function getControlPlaneExecutionPolicy(agentId: string) {
  return controlPlaneFetchJson<ControlPlaneExecutionPolicyPayload>(
    `/api/control-plane/agents/${agentId}/execution-policy`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.agent(agentId)],
    },
  );
}

export async function getControlPlaneExecutionPolicyCatalog(agentId: string) {
  return controlPlaneFetchJson<{
    agent_id: string;
    catalog: ControlPlaneExecutionPolicyCatalog;
    policy: ControlPlaneExecutionPolicy;
  }>(`/api/control-plane/agents/${agentId}/policy-catalog`, {}, {
    tier: "detail",
    tags: [CONTROL_PLANE_CACHE_TAGS.agent(agentId)],
  });
}

export async function evaluateControlPlaneExecutionPolicy(
  agentId: string,
  payload: {
    policy?: ControlPlaneExecutionPolicy;
    action?: Record<string, unknown>;
    envelope?: Record<string, unknown>;
    [key: string]: unknown;
  },
) {
  return controlPlaneFetchJson<ControlPlaneExecutionPolicyEvaluation>(
    `/api/control-plane/agents/${agentId}/execution-policy/evaluate`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.agent(agentId)],
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

export async function getControlPlaneRuntimeAccess(agentId: string) {
  return controlPlaneFetchJson<ControlPlaneRuntimeAccess>(
    `/api/control-plane/agents/${agentId}/runtime-access`,
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
  agentId: string,
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
    `/api/control-plane/agents/${agentId}/runtime-access${suffix}`,
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

export async function getControlPlaneOnboardingStatus() {
  return controlPlaneFetchJson<ControlPlaneOnboardingStatus>(
    "/api/control-plane/onboarding/status",
    {},
    { tier: "live" },
  );
}

export async function getControlPlaneAuthStatus() {
  return controlPlaneFetchJson<ControlPlaneAuthStatus>(
    "/api/control-plane/auth/status",
    {},
    { tier: "live" },
  );
}

export async function getControlPlaneConnectionCatalog() {
  return controlPlaneFetchJson<{ items: ControlPlaneConnectionCatalogEntry[] }>(
    "/api/control-plane/connections/catalog",
    {},
    {
      tier: "catalog",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}

export async function getControlPlaneConnectionDefaults() {
  return controlPlaneFetchJson<{ items: ControlPlaneAgentConnection[] }>(
    "/api/control-plane/connections/defaults",
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.core],
    },
  );
}

function deriveCoreConnectionStatus(connection?: ControlPlaneAgentConnection | null) {
  return String(connection?.status || "not_configured");
}

function toCoreIntegrationConnection(
  integration: ControlPlaneConnectionCatalogEntry,
  connection?: ControlPlaneAgentConnection | null,
): ControlPlaneCoreIntegrationConnection {
  const authModes = Array.isArray(integration.auth_capabilities?.modes)
    ? integration.auth_capabilities?.modes.map((item) => String(item))
    : [];
  const status = deriveCoreConnectionStatus(connection);
  const metadata =
    connection?.metadata && typeof connection.metadata === "object" ? connection.metadata : {};

  return {
    connection_key: connection?.connection_key || integration.connection_key,
    kind: "core",
    integration_key: integration.integration_key,
    integration_id: integration.integration_key,
    title: integration.display_name,
    description: integration.description,
    transport: integration.transport_kind || undefined,
    auth_modes: authModes,
    auth_mode: String(connection?.auth_method || connection?.auth_strategy || integration.auth_strategy_default || authModes[0] || "none"),
    auth_method: connection?.auth_method || connection?.auth_strategy || integration.auth_strategy_default || undefined,
    auth_strategy: connection?.auth_strategy || integration.auth_strategy_default || undefined,
    source_origin: connection?.source_origin || "system_default",
    configured: Boolean(connection?.connected),
    verified: status === "verified",
    account_label: connection?.account_label || "",
    provider_account_id: connection?.provider_account_id || null,
    expires_at: connection?.expires_at || null,
    last_verified_at: connection?.last_verified_at || "",
    last_error: connection?.last_error || "",
    checked_via:
      typeof metadata.checked_via === "string"
        ? metadata.checked_via
        : "",
    auth_expired:
      typeof metadata.auth_expired === "boolean"
        ? metadata.auth_expired
        : false,
    metadata,
    fields: Array.isArray(connection?.fields) ? connection?.fields : [],
    health_probe:
      typeof metadata.health_probe === "string"
        ? metadata.health_probe
        : "",
    supports_persistence: Boolean(metadata.supports_persistence ?? true),
    connection_status: status,
    status,
    connected: Boolean(connection?.connected),
    enabled: Boolean(connection?.enabled ?? connection?.connected),
    tool_count: connection?.tool_count ?? 0,
  };
}

export async function getControlPlaneCoreIntegrations() {
  const [catalog, defaults] = await Promise.all([
    getControlPlaneConnectionCatalog(),
    getControlPlaneConnectionDefaults(),
  ]);
  const defaultMap = new Map(
    (defaults.items || [])
      .filter((item) => item.kind === "core")
      .map((item) => [item.integration_key, item] as const),
  );

  const items = (catalog.items || [])
    .filter((item) => item.kind === "core")
    .map((item) => {
      const connection = defaultMap.get(item.integration_key) || null;
      const authModes = Array.isArray(item.auth_capabilities?.modes)
        ? item.auth_capabilities?.modes.map((mode) => String(mode))
        : [];
      return {
        id: item.integration_key,
        integration_id: item.integration_key,
        title: item.display_name,
        description: item.description,
        enabled: Boolean(connection?.enabled ?? connection?.connected),
        configured: Boolean(connection?.connected),
        category: item.category,
        transport: item.transport_kind || undefined,
        auth_modes: authModes,
        auth_mode: String(connection?.auth_method || connection?.auth_strategy || item.auth_strategy_default || authModes[0] || "none"),
        connection_status: deriveCoreConnectionStatus(connection),
        health_probe:
          typeof connection?.metadata?.health_probe === "string"
            ? connection.metadata.health_probe
            : "",
        supports_persistence: Boolean(connection?.metadata?.supports_persistence ?? true),
        connection: toCoreIntegrationConnection(item, connection),
      } satisfies ControlPlaneCoreIntegration;
    });

  return {
    items,
    governance: {
      ownership: "core",
      source_of_truth: "connections_catalog_and_defaults",
    },
  } satisfies ControlPlaneCoreIntegrations;
}

/* -------------------------------------------------------------------------- */
/*  Workspace / Squad spec API                                                 */
/* -------------------------------------------------------------------------- */

export async function getWorkspaceSpec(workspaceId: string) {
  return controlPlaneFetchJson<{ spec: WorkspaceSpec; documents: ScopePromptDocuments }>(
    `/api/control-plane/workspaces/${workspaceId}/spec`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.workspaces],
    },
  );
}

export async function updateWorkspaceSpec(
  workspaceId: string,
  payload: { spec: WorkspaceSpec; documents?: ScopePromptDocuments },
) {
  return controlPlaneFetchJson<{ spec: WorkspaceSpec; documents: ScopePromptDocuments }>(
    `/api/control-plane/workspaces/${workspaceId}/spec`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function getSquadSpec(workspaceId: string, squadId: string) {
  return controlPlaneFetchJson<{ spec: SquadSpec; documents: ScopePromptDocuments }>(
    `/api/control-plane/workspaces/${workspaceId}/squads/${squadId}/spec`,
    {},
    {
      tier: "detail",
      tags: [CONTROL_PLANE_CACHE_TAGS.workspaces],
    },
  );
}

export async function updateSquadSpec(
  workspaceId: string,
  squadId: string,
  payload: { spec: SquadSpec; documents?: ScopePromptDocuments },
) {
  return controlPlaneFetchJson<{ spec: SquadSpec; documents: ScopePromptDocuments }>(
    `/api/control-plane/workspaces/${workspaceId}/squads/${squadId}/spec`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}
