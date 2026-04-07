"use client";

import { useMemo } from "react";
import { Check, Cpu, Server, Volume2 } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  FormCurrencyInput,
  FormField,
  FormInput,
  FormSelect,
  FormTextarea,
} from "@/components/control-plane/shared/form-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { ModelSelector } from "@/components/control-plane/shared/model-selector";
import { AnimatePresence, motion } from "framer-motion";
import { FADE_TRANSITION, COLLAPSE_TRANSITION } from "@/components/control-plane/shared/motion-constants";
import { cn } from "@/lib/utils";
import {
  parseModelPolicy,
  parseResponsePolicy,
  parseVoicePolicy,
  serializeModelPolicy,
  serializeVoicePolicy,
} from "@/lib/policy-serializers";

function unique(items: string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function prettifyModelId(modelId: string) {
  if (!modelId) return "";
  return modelId
    .replace(/:latest$/i, "")
    .replace(/[-_]/g, " ")
    .replace(/\b(\d+(?:\.\d+)?)\b/g, "$1")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .replace(/\bGpt\b/g, "GPT")
    .replace(/\bOss\b/g, "OSS");
}

const PROVIDER_LOGOS: Record<string, string> = {
  claude: "/providers/anthropic.svg",
  codex: "/providers/openai.svg",
  gemini: "/providers/google.svg",
  ollama: "/providers/ollama.png",
};

const PROVIDER_ACCENTS: Record<string, string> = {
  claude: "212 120 62",
  codex: "16 163 127",
  gemini: "86 138 248",
  ollama: "56 189 248",
};

function providerDescription(providerId: string, title: string) {
  if (providerId === "claude") {
    return "Raciocínio forte";
  }
  if (providerId === "codex") {
    return "Execução geral";
  }
  if (providerId === "gemini") {
    return "Contexto amplo";
  }
  if (providerId === "ollama") {
    return "Execução local";
  }
  return title;
}

function ProviderLogo({
  providerId,
  active = false,
  size = "md",
}: {
  providerId: string;
  active?: boolean;
  size?: "sm" | "md";
}) {
  const accent = PROVIDER_ACCENTS[providerId] || "255 255 255";
  const accentColor = `rgb(${accent})`;
  const logo = PROVIDER_LOGOS[providerId];
  const wrapperClass = size === "sm" ? "h-8 w-8 rounded-xl" : "h-11 w-11 rounded-2xl";
  const iconClass = size === "sm" ? "h-4 w-4" : "h-6 w-6";
  const fallbackIconClass = size === "sm" ? "h-4 w-4" : "h-5 w-5";

  if (logo) {
    return (
      <div
        className={`flex items-center justify-center border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] transition-colors ${wrapperClass}`}
        style={
          active
            ? {
                borderColor: `rgba(${accent}, 0.34)`,
                backgroundColor: `rgba(${accent}, 0.1)`,
              }
            : undefined
        }
      >
        <span
          className={`block ${iconClass}`}
          style={{
            backgroundColor: active ? accentColor : "rgb(255 255 255)",
            WebkitMaskImage: `url(${logo})`,
            maskImage: `url(${logo})`,
            WebkitMaskRepeat: "no-repeat",
            maskRepeat: "no-repeat",
            WebkitMaskPosition: "center",
            maskPosition: "center",
            WebkitMaskSize: "contain",
            maskSize: "contain",
          }}
        />
      </div>
    );
  }

  return (
    <div
      className={`flex items-center justify-center border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] transition-colors ${wrapperClass}`}
      style={
        active
          ? {
              borderColor: `rgba(${accent}, 0.34)`,
              backgroundColor: `rgba(${accent}, 0.1)`,
            }
            : undefined
      }
    >
      <Server
        className={fallbackIconClass}
        style={{ color: active ? accentColor : "rgb(255 255 255 / 0.86)" }}
      />
    </div>
  );
}

export function TabRecursos() {
  const { state, core, developerMode, updateAgentSpecField, updateDocument } = useBotEditor();
  const { tl } = useAppI18n();

  const modelPolicy = useMemo(
    () => parseModelPolicy(state.modelPolicyJson),
    [state.modelPolicyJson],
  );
  const voicePolicy = useMemo(
    () => parseVoicePolicy(state.voicePolicyJson),
    [state.voicePolicyJson],
  );

  const providerEntries = useMemo(
    () => core.providers.providers ?? {},
    [core.providers.providers],
  );
  const enabledProviders = useMemo(() => {
    const configured = Array.isArray(core.providers.enabled_providers)
      ? core.providers.enabled_providers.map(String)
      : [];
    if (configured.length > 0) return configured;
    return Object.entries(providerEntries)
      .filter(([, payload]) => Boolean(payload.enabled))
      .map(([provider]) => provider);
  }, [core.providers.enabled_providers, providerEntries]);
  const generalProviders = useMemo(
    () =>
      enabledProviders.filter(
        (provider) => String(providerEntries[provider]?.category || "general") === "general",
      ),
    [enabledProviders, providerEntries],
  );
  const providerOptions = useMemo(
    () =>
      generalProviders.map((provider) => ({
        value: provider,
        label: String(providerEntries[provider]?.title || providerEntries[provider]?.vendor || provider),
      })),
    [generalProviders, providerEntries],
  );
  const requestedAllowedProviders = modelPolicy.allowed_providers.filter((provider) =>
    generalProviders.includes(provider),
  );
  const effectiveAllowedProviders =
    requestedAllowedProviders.length > 0 ? requestedAllowedProviders : generalProviders;
  const effectiveDefaultProvider = effectiveAllowedProviders.includes(modelPolicy.default_provider)
    ? modelPolicy.default_provider
    : effectiveAllowedProviders[0] || generalProviders[0] || "";
  const availableModels =
    modelPolicy.available_models_by_provider[effectiveDefaultProvider] ??
    (Array.isArray(providerEntries[effectiveDefaultProvider]?.available_models)
      ? providerEntries[effectiveDefaultProvider].available_models.map(String)
      : []);
  const defaultModel =
    modelPolicy.default_models[effectiveDefaultProvider] || availableModels[0] || "";
  const modelFunctions = Array.isArray((core.providers as Record<string, unknown>).model_functions)
    ? ((core.providers as Record<string, unknown>).model_functions as Array<Record<string, unknown>>)
    : [];
  const functionalModelCatalog = useMemo(
    () =>
      (((core.providers as Record<string, unknown>).functional_model_catalog ?? {}) as Record<
        string,
        Array<Record<string, unknown>>
      >),
    [core.providers],
  );
  const generalModelLabelMap = useMemo(() => {
    const generalItems = functionalModelCatalog.general || [];
    return generalItems.reduce<Record<string, string>>((accumulator, item) => {
      const providerId = String(item.provider_id || "").trim();
      const modelId = String(item.model_id || "").trim();
      const title = String(item.title || "").trim();
      if (providerId && modelId && title) {
        accumulator[`${providerId}:${modelId}`] = title;
      }
      return accumulator;
    }, {});
  }, [functionalModelCatalog]);

  const currentModelLabel =
    (defaultModel
      ? generalModelLabelMap[`${effectiveDefaultProvider}:${defaultModel}`] || prettifyModelId(defaultModel)
      : "") || tl("Nenhum modelo selecionado");
  const currentProviderLabel =
    providerOptions.find((item) => item.value === effectiveDefaultProvider)?.label ??
    (effectiveDefaultProvider || tl("Nenhum provider selecionado"));
  const voiceModeLabel =
    voicePolicy.mode === "tts"
      ? tl("Leitura em voz")
      : voicePolicy.mode === "voice_active"
        ? tl("Fala ativa")
        : tl("Desligado");

  function updateModelPolicy(next: Partial<typeof modelPolicy>) {
    const allowedProviders = unique(
      (next.allowed_providers ?? effectiveAllowedProviders).filter((provider) =>
        generalProviders.includes(provider),
      ),
    );
    const defaultProviderCandidate =
      next.default_provider ?? modelPolicy.default_provider ?? effectiveDefaultProvider;
    const defaultProvider = allowedProviders.includes(defaultProviderCandidate)
      ? defaultProviderCandidate
      : allowedProviders[0] || "";
    const fallbackOrder = defaultProvider
      ? [defaultProvider, ...allowedProviders.filter((provider) => provider !== defaultProvider)]
      : [];

    const availableModelsByProvider = { ...modelPolicy.available_models_by_provider };
    const defaultModels = { ...modelPolicy.default_models };
    const tierModels = { ...modelPolicy.tier_models };

    for (const provider of Object.keys(availableModelsByProvider)) {
      if (!allowedProviders.includes(provider)) {
        delete availableModelsByProvider[provider];
        delete defaultModels[provider];
        delete tierModels[provider];
      }
    }

    for (const provider of allowedProviders) {
      const providerModels = Array.isArray(providerEntries[provider]?.available_models)
        ? providerEntries[provider].available_models.map(String)
        : [];
      if (providerModels.length > 0) {
        availableModelsByProvider[provider] = providerModels;
      }
      const providerDefault =
        next.default_models?.[provider] ||
        defaultModels[provider] ||
        providerModels[0] ||
        "";
      if (providerDefault) {
        defaultModels[provider] = providerDefault;
        tierModels[provider] = {
          ...tierModels[provider],
          medium: tierModels[provider]?.medium || providerDefault,
        };
      }
    }

    updateAgentSpecField(
      "modelPolicyJson",
      serializeModelPolicy({
        ...modelPolicy,
        ...next,
        allowed_providers: allowedProviders,
        default_provider: defaultProvider,
        fallback_order: fallbackOrder,
        available_models_by_provider: availableModelsByProvider,
        default_models: defaultModels,
        tier_models: tierModels,
      }),
    );
  }

  const responsePolicy = useMemo(
    () => parseResponsePolicy(state.responsePolicyJson),
    [state.responsePolicyJson],
  );

  function updateVoicePolicy(patch: Partial<typeof voicePolicy>) {
    const next = { ...voicePolicy, ...patch };
    // Auto-set sensible defaults when voice is first enabled
    if (patch.mode && patch.mode !== "disabled" && voicePolicy.mode === "disabled") {
      if (!next.style) {
        next.style = "natural e conversacional";
      }
      if (!next.tts_notes) {
        const lang = responsePolicy.language === "en-US" ? "English"
          : responsePolicy.language === "es-ES" ? "Spanish"
          : "Portuguese";
        next.tts_notes = `Escreva o texto como realmente se fala em ${lang}. Evite caracteres especiais, abreviacoes, e formatacao Markdown. O audio deve soar natural e fluente.`;
      }
      // Seed voice prompt if empty
      if (!state.documents.voice_prompt_md) {
        const lang = responsePolicy.language === "en-US" ? "English"
          : responsePolicy.language === "es-ES" ? "Spanish"
          : "Portuguese";
        updateDocument("voice_prompt_md",
          `Ao gerar texto para audio, siga estas regras:\n\n` +
          `- Escreva exatamente como uma pessoa falaria em ${lang}\n` +
          `- Nao use caracteres especiais (*, #, [], etc.)\n` +
          `- Nao use abreviacoes — escreva por extenso\n` +
          `- Numeros devem ser escritos por extenso quando curtos\n` +
          `- O tom deve ser ${next.style || "natural e conversacional"}\n` +
          `- O audio pode ser longo o quanto necessario para uma resposta completa\n`
        );
      }
    }
    updateAgentSpecField(
      "voicePolicyJson",
      serializeVoicePolicy(next),
    );
  }

  function toggleAllowedProvider(provider: string) {
    const nextProviders = effectiveAllowedProviders.includes(provider)
      ? effectiveAllowedProviders.length > 1
        ? effectiveAllowedProviders.filter((item) => item !== provider)
        : effectiveAllowedProviders
      : [...effectiveAllowedProviders, provider];
    updateModelPolicy({ allowed_providers: nextProviders });
  }

  return (
    <div className="flex flex-col gap-6">
      <PolicyCard
        title={tl("Modelo principal")}
        description={`${currentProviderLabel} · ${currentModelLabel}`}
        icon={Cpu}
        dirty={state.dirty.agentSpec}
      >
        <div className="flex flex-wrap gap-2">
          <span className="chip text-xs">{currentProviderLabel}</span>
          <span className="chip text-xs font-mono">{currentModelLabel}</span>
          {modelPolicy.fallback_order.length > 0 ? (
            <span className="chip text-xs">
              {tl("Fallback")}: {modelPolicy.fallback_order.join(" → ")}
            </span>
          ) : null}
        </div>

        <FormField label={tl("Providers disponíveis")}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {providerOptions.map((provider) => {
              const isAllowed = effectiveAllowedProviders.includes(provider.value);
              return (
                <button
                  key={provider.value}
                  type="button"
                  onClick={() => toggleAllowedProvider(provider.value)}
                  className={cn(
                    "flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-all",
                    isAllowed
                      ? "border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.04)]"
                      : "border-[rgba(255,255,255,0.05)] bg-transparent opacity-50",
                  )}
                >
                  <ProviderLogo providerId={provider.value} active={isAllowed} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-[var(--text-primary)]">{provider.label}</div>
                    <div className="truncate text-[10px] text-[var(--text-quaternary)]">{providerDescription(provider.value, provider.label)}</div>
                  </div>
                  {isAllowed && (
                    <Check size={12} className="shrink-0 text-[var(--text-tertiary)]" />
                  )}
                </button>
              );
            })}
          </div>
        </FormField>

        {effectiveAllowedProviders.length > 1 && (
          <FormField label={tl("Provider principal")}>
            <div className="flex flex-wrap gap-2">
              {effectiveAllowedProviders.map((providerId) => {
                const title =
                  providerOptions.find((item) => item.value === providerId)?.label ?? providerId;
                const isDefault = effectiveDefaultProvider === providerId;
                return (
                  <button
                    key={providerId}
                    type="button"
                    onClick={() => updateModelPolicy({ default_provider: providerId })}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all",
                      isDefault
                        ? "border-[rgba(255,255,255,0.16)] bg-[rgba(255,255,255,0.06)] text-[var(--text-primary)]"
                        : "border-[rgba(255,255,255,0.06)] text-[var(--text-tertiary)] hover:border-[rgba(255,255,255,0.12)]",
                    )}
                  >
                    <ProviderLogo providerId={providerId} active={isDefault} size="sm" />
                    {title}
                    {isDefault && <Check size={10} />}
                  </button>
                );
              })}
            </div>
          </FormField>
        )}

        <motion.div
          key={effectiveDefaultProvider}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={FADE_TRANSITION}
        >
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(220px,0.7fr)_minmax(220px,0.7fr)]">
            <ModelSelector
              label={tl("Modelo principal")}
              value={`${effectiveDefaultProvider}:${defaultModel}`}
              onChange={(combined) => {
                const [pId, ...mParts] = combined.split(":");
                const mId = mParts.join(":");
                updateModelPolicy({
                  default_provider: pId,
                  default_models: {
                    ...modelPolicy.default_models,
                    [pId]: mId,
                  },
                  tier_models: {
                    ...modelPolicy.tier_models,
                    [pId]: {
                      ...(modelPolicy.tier_models[pId] || {}),
                      medium: mId,
                    },
                  },
                });
              }}
              providers={providerEntries}
              enabledProviders={generalProviders}
              functionalCatalog={functionalModelCatalog}
              functionId="general"
            />

            <FormCurrencyInput
              label={tl("Orçamento por tarefa (USD)")}
              value={modelPolicy.max_budget_usd}
              onValueChange={(value) =>
                updateModelPolicy({
                  max_budget_usd: value,
                })
              }
              placeholder="US$ 0,00"
            />

            <FormCurrencyInput
              label={tl("Orçamento total (USD)")}
              value={modelPolicy.max_total_budget_usd}
              onValueChange={(value) =>
                updateModelPolicy({
                  max_total_budget_usd: value,
                })
              }
              placeholder="US$ 0,00"
            />
          </div>
        </motion.div>

        {modelFunctions.length > 0 ? (
          <SectionCollapsible title={tl("Modelos especializados por tipo de tarefa")}>
            <div className="flex flex-col gap-4 pt-2">
              {modelFunctions.map((functionItem) => {
                const fnId = String(functionItem.id || "");
                const currentSelection = modelPolicy.functional_defaults[fnId];
                const fnValue =
                  currentSelection?.provider_id && currentSelection?.model_id
                    ? `${currentSelection.provider_id}:${currentSelection.model_id}`
                    : "";
                return (
                  <ModelSelector
                    key={fnId}
                    label={String(functionItem.title || fnId)}
                    value={fnValue}
                    onChange={(combined) => {
                      const nextDefaults = { ...modelPolicy.functional_defaults };
                      if (!combined) {
                        delete nextDefaults[fnId];
                      } else {
                        const [pId, ...mParts] = combined.split(":");
                        nextDefaults[fnId] = {
                          provider_id: pId,
                          model_id: mParts.join(":"),
                        };
                      }
                      updateModelPolicy({ functional_defaults: nextDefaults });
                    }}
                    providers={providerEntries}
                    enabledProviders={generalProviders}
                    functionalCatalog={functionalModelCatalog}
                    functionId={fnId}
                    emptyLabel="Herdar do modelo principal"
                  />
                );
              })}
            </div>
          </SectionCollapsible>
        ) : null}
      </PolicyCard>

      <PolicyCard
        title={tl("Voz")}
        description={voiceModeLabel}
        icon={Volume2}
      >
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
          <FormSelect
            label={tl("Modo de voz")}
            value={voicePolicy.mode}
            onChange={(event) => updateVoicePolicy({ mode: event.target.value })}
            options={[
              { value: "disabled", label: tl("Desligado") },
              { value: "tts", label: tl("Leitura em voz") },
              { value: "voice_active", label: tl("Fala ativa") },
            ]}
          />
          <FormInput
            label={tl("Estilo da fala")}
            value={voicePolicy.style}
            onChange={(event) => updateVoicePolicy({ style: event.target.value })}
            placeholder={tl("Ex: calmo e objetivo")}
          />
        </div>

        {voicePolicy.mode !== "disabled" && (
          <FormTextarea
            label={tl("Notas de TTS")}
            description={tl("Orientacoes para o modelo ao gerar texto para audio.")}
            value={voicePolicy.tts_notes}
            onChange={(event) => updateVoicePolicy({ tts_notes: event.target.value })}
            placeholder={tl("Ex: evitar caracteres especiais, escrever como se fala, numeros por extenso")}
            rows={2}
          />
        )}

        <MarkdownEditorField
          label={tl("Prompt de voz")}
          value={state.documents.voice_prompt_md ?? ""}
          onChange={(value) => updateDocument("voice_prompt_md", value)}
          minHeight="220px"
        />
      </PolicyCard>

      <AnimatePresence>
        {developerMode && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={COLLAPSE_TRANSITION}
            className="overflow-hidden"
          >
            <SectionCollapsible title={tl("JSON avançado")}>
              <div className="flex flex-col gap-6 pt-2">
                <JsonEditorField
                  label={tl("Política de modelo (JSON)")}
                  description={tl("Contrato canônico que o runtime realmente materializa.")}
                  value={state.modelPolicyJson}
                  onChange={(value) => updateAgentSpecField("modelPolicyJson", value)}
                />
                <JsonEditorField
                  label={tl("Política de voz (JSON)")}
                  description={tl("Override avançado de voz e TTS.")}
                  value={state.voicePolicyJson}
                  onChange={(value) => updateAgentSpecField("voicePolicyJson", value)}
                />

                <SectionCollapsible title={tl("Políticas descontinuadas")}>
                  <div className="flex flex-col gap-6 pt-2">
                    <JsonEditorField
                      label={tl("Política de tools (JSON)")}
                      description={tl("Subset efetivo do catálogo de tools do core.")}
                      value={state.toolPolicyJson}
                      onChange={(value) => updateAgentSpecField("toolPolicyJson", value)}
                    />
                    <JsonEditorField
                      label={tl("Política de imagem (JSON)")}
                      description={tl("Override avançado para análise visual.")}
                      value={state.imageAnalysisPolicyJson}
                      onChange={(value) => updateAgentSpecField("imageAnalysisPolicyJson", value)}
                    />
                  </div>
                </SectionCollapsible>
              </div>
            </SectionCollapsible>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
