"use client";

import type {
  GeneralSystemSettings,
  GeneralSystemSettingsValueSource,
  GeneralSystemSettingsVariable,
} from "@/lib/control-plane";
import { translateLiteral } from "@/lib/i18n";

// --- Section-based navigation ---

export type SettingsSectionId = "general" | "models" | "integrations" | "intelligence";

export const SETTINGS_SECTIONS: Array<{
  id: SettingsSectionId;
  labelKey: string;
  descriptionKey: string;
  icon: string;
}> = [
  {
    id: "general",
    labelKey: "settings.sections.general.label",
    descriptionKey: "settings.sections.general.description",
    icon: "User",
  },
  {
    id: "models",
    labelKey: "settings.sections.models.label",
    descriptionKey: "settings.sections.models.description",
    icon: "Cpu",
  },
  {
    id: "integrations",
    labelKey: "settings.sections.integrations.label",
    descriptionKey: "settings.sections.integrations.description",
    icon: "Plug",
  },
  {
    id: "intelligence",
    labelKey: "settings.sections.intelligence.label",
    descriptionKey: "settings.sections.intelligence.description",
    icon: "Brain",
  },
];

/** Maps each section to the `GeneralSystemSettings.values` keys it owns.
 *  Used for per-section dirty tracking and discard. */
export const SECTION_VALUE_KEYS: Record<
  SettingsSectionId,
  Array<keyof GeneralSystemSettings["values"]>
> = {
  general: ["account"],
  models: ["models", "provider_connections"],
  integrations: ["resources", "integration_credentials"],
  intelligence: ["memory_and_knowledge", "variables"],
};

/** Maps old step IDs to new section IDs for localStorage migration */
export const STEP_TO_SECTION: Record<string, SettingsSectionId> = {
  account: "general",
  models: "models",
  integrations: "integrations",
  memory: "intelligence",
  variables: "intelligence",
  review: "general",
};

export const AGENT_ONLY_INTEGRATIONS = new Set([
  "browser_enabled",
  "docker_enabled",
  "whisper_enabled",
  "tts_enabled",
  "link_analysis_enabled",
]);

export function sourceBadgeLabel(source: GeneralSystemSettingsValueSource) {
  if (source === "custom") return translateLiteral("Personalizado");
  if (source === "env") return translateLiteral("Vindo do .env");
  return translateLiteral("Padrão do sistema");
}

export function sourceBadgeTone(source: GeneralSystemSettingsValueSource) {
  if (source === "custom") return "text-emerald-200 border-emerald-500/30 bg-emerald-500/10";
  if (source === "env") return "text-sky-200 border-sky-500/30 bg-sky-500/10";
  return "text-zinc-300 border-white/10 bg-white/5";
}

export function normalizeFallbackOrder(
  enabledProviders: string[],
  requestedOrder: string[],
  defaultProvider: string,
) {
  const enabledSet = new Set(enabledProviders);
  const unique: string[] = [];
  const push = (provider: string) => {
    if (!provider || !enabledSet.has(provider) || unique.includes(provider)) {
      return;
    }
    unique.push(provider);
  };

  push(defaultProvider);
  for (const provider of requestedOrder) {
    push(provider);
  }
  for (const provider of enabledProviders) {
    push(provider);
  }
  return unique;
}

export function sanitizeVariableDraft(
  variable: Partial<GeneralSystemSettingsVariable>,
): GeneralSystemSettingsVariable {
  return {
    key: String(variable.key ?? "")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_]/g, "_")
      .replace(/^_+|_+$/g, ""),
    type: variable.type === "secret" ? "secret" : "text",
    scope: variable.scope === "bot_grant" ? "bot_grant" : "system_only",
    description: String(variable.description ?? "").trim(),
    value: String(variable.value ?? ""),
    preview: String(variable.preview ?? ""),
    value_present: Boolean(variable.value_present),
    clear: Boolean(variable.clear),
  };
}

export function upsertVariable(
  variables: GeneralSystemSettingsVariable[],
  nextVariable: GeneralSystemSettingsVariable,
) {
  const sanitized = sanitizeVariableDraft(nextVariable);
  const next = variables.filter((item) => item.key !== sanitized.key);
  next.push(sanitized);
  return next.sort((left, right) => left.key.localeCompare(right.key));
}

export function removeVariable(
  variables: GeneralSystemSettingsVariable[],
  variableKey: string,
) {
  return variables.filter((item) => item.key !== variableKey);
}

export function cloneGeneralSystemSettings(
  settings: GeneralSystemSettings,
): GeneralSystemSettings {
  const cloned = JSON.parse(JSON.stringify(settings)) as GeneralSystemSettings;
  if (!cloned.values.provider_connections) {
    cloned.values.provider_connections = {};
  }
  if (!cloned.values.models.functional_defaults) {
    cloned.values.models.functional_defaults = {};
  }
  if (!cloned.values.memory_and_knowledge.memory_policy) {
    cloned.values.memory_and_knowledge.memory_policy = {};
  }
  if (!cloned.values.memory_and_knowledge.knowledge_policy) {
    cloned.values.memory_and_knowledge.knowledge_policy = {};
  }
  if (!cloned.values.memory_and_knowledge.autonomy_policy) {
    cloned.values.memory_and_knowledge.autonomy_policy = {};
  }
  if (!cloned.catalogs.model_functions) {
    cloned.catalogs.model_functions = [];
  }
  if (!cloned.catalogs.functional_model_catalog) {
    cloned.catalogs.functional_model_catalog = {};
  }
  if (!cloned.catalogs.knowledge_layers) {
    cloned.catalogs.knowledge_layers = [];
  }
  if (!cloned.catalogs.approval_modes) {
    cloned.catalogs.approval_modes = [];
  }
  if (!cloned.catalogs.autonomy_tiers) {
    cloned.catalogs.autonomy_tiers = [];
  }
  return cloned;
}
