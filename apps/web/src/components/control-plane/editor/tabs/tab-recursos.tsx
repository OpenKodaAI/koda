"use client";

import { useMemo } from "react";
import { Check, Cpu, ImageIcon, Server, Volume2, Wrench } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  FormCurrencyInput,
  FormField,
  FormInput,
  FormSelect,
} from "@/components/control-plane/shared/form-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { TagInputField } from "@/components/control-plane/shared/tag-input-field";
import { cn } from "@/lib/utils";
import {
  parseImageAnalysisPolicy,
  parseModelPolicy,
  parseToolPolicy,
  parseVoicePolicy,
  serializeImageAnalysisPolicy,
  serializeModelPolicy,
  serializeToolPolicy,
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
    .replace(/\bOss\b/g, "OSS")
    .replace(/\bQwen\b/g, "Qwen")
    .replace(/\bLlama\b/g, "Llama");
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

function ProviderChoiceCard({
  title,
  description,
  providerId,
  selected,
  emphasized = false,
  badge,
  onClick,
  className,
}: {
  title: string;
  description?: string;
  providerId: string;
  selected: boolean;
  emphasized?: boolean;
  badge?: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-start gap-3 rounded-2xl border px-4 py-4 text-left shadow-none transition-colors",
        className,
      )}
      style={{
        borderColor: selected ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.06)",
        backgroundColor: selected
          ? emphasized
            ? "rgba(255,255,255,0.06)"
            : "rgba(255,255,255,0.04)"
          : "rgba(255,255,255,0.015)",
      }}
    >
      <ProviderLogo providerId={providerId} active={selected} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-[var(--text-primary)]">{title}</span>
          {badge ? (
            <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
              {badge}
            </span>
          ) : null}
        </div>
        {description ? (
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-tertiary)]">{description}</p>
        ) : null}
      </div>
      {selected ? (
        <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[rgba(255,255,255,0.08)] text-[var(--text-primary)]">
          <Check size={12} />
        </span>
      ) : null}
    </button>
  );
}

function ToolChoiceCard({
  title,
  description,
  selected,
  onClick,
  className,
}: {
  title: string;
  description: string;
  selected: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-start gap-3 rounded-2xl border px-4 py-4 text-left shadow-none transition-colors",
        selected
          ? "border-[rgba(255,255,255,0.16)] bg-[rgba(255,255,255,0.045)]"
          : "border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.015)] hover:bg-[rgba(255,255,255,0.025)]",
        className,
      )}
    >
      <span
        className={cn(
          "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border",
          selected
            ? "border-[rgba(255,255,255,0.18)] bg-[rgba(255,255,255,0.08)] text-white"
            : "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] text-[var(--text-secondary)]",
        )}
      >
        <Wrench size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-[var(--text-primary)]">{title}</span>
        <span className="mt-1 block text-xs leading-relaxed text-[var(--text-tertiary)]">
          {description}
        </span>
      </span>
      {selected ? (
        <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[rgba(255,255,255,0.08)] text-[var(--text-primary)]">
          <Check size={12} />
        </span>
      ) : null}
    </button>
  );
}

export function TabRecursos() {
  const { state, core, developerMode, updateAgentSpecField, updateDocument } = useBotEditor();
  const { tl } = useAppI18n();

  const modelPolicy = useMemo(
    () => parseModelPolicy(state.modelPolicyJson),
    [state.modelPolicyJson],
  );
  const toolPolicy = useMemo(
    () => parseToolPolicy(state.toolPolicyJson),
    [state.toolPolicyJson],
  );
  const voicePolicy = useMemo(
    () => parseVoicePolicy(state.voicePolicyJson),
    [state.voicePolicyJson],
  );
  const imagePolicy = useMemo(
    () => parseImageAnalysisPolicy(state.imageAnalysisPolicyJson),
    [state.imageAnalysisPolicyJson],
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

  const availableTools = useMemo(
    () =>
      (core.tools.items ?? [])
        .filter((item) => Boolean(item.available))
        .map((item) => ({
          value: String(item.id),
          label: String(item.title || item.id),
          description: String(
            item.summary ||
              item.description ||
              "Capacidade disponível no core para tarefas especializadas.",
          ),
        })),
    [core.tools.items],
  );
  const effectiveAllowedTools =
    toolPolicy.allowed_tool_ids.length > 0
      ? toolPolicy.allowed_tool_ids
      : availableTools.map((item) => item.value);
  const currentModelLabel =
    (defaultModel
      ? generalModelLabelMap[`${effectiveDefaultProvider}:${defaultModel}`] || prettifyModelId(defaultModel)
      : "") || tl("Nenhum modelo selecionado");
  const currentProviderLabel =
    providerOptions.find((item) => item.value === effectiveDefaultProvider)?.label ??
    (effectiveDefaultProvider || tl("Nenhum provider selecionado"));
  const defaultModelOptions =
    availableModels.length > 0
      ? availableModels.map((model) => ({
          value: model,
          label:
            generalModelLabelMap[`${effectiveDefaultProvider}:${model}`] || prettifyModelId(model),
          description: model,
          group: currentProviderLabel,
          icon: (
            <ProviderLogo
              providerId={effectiveDefaultProvider}
              active
              size="sm"
            />
          ),
        }))
      : [{ value: "", label: tl("Nenhum modelo disponível") }];
  const toolsSummaryLabel =
    effectiveAllowedTools.length > 0
      ? `${effectiveAllowedTools.length} tool(s) ativas`
      : tl("Nenhuma tool ativa");
  const imageModeLabel =
    imagePolicy.fallback_behavior === "strict"
      ? tl("Conservador")
      : imagePolicy.fallback_behavior === "summarize"
        ? tl("Resumo visual")
        : tl("Descrever e analisar");
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

  function updateToolPolicy(nextAllowedToolIds: string[]) {
    updateAgentSpecField(
      "toolPolicyJson",
      serializeToolPolicy({
        ...toolPolicy,
        allowed_tool_ids: unique(nextAllowedToolIds),
      }),
    );
  }

  function updateVoicePolicy(patch: Partial<typeof voicePolicy>) {
    updateAgentSpecField(
      "voicePolicyJson",
      serializeVoicePolicy({ ...voicePolicy, ...patch }),
    );
  }

  function updateImagePolicy(patch: Partial<typeof imagePolicy>) {
    updateAgentSpecField(
      "imageAnalysisPolicyJson",
      serializeImageAnalysisPolicy({ ...imagePolicy, ...patch }),
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

  function toggleAllowedTool(toolId: string) {
    const next = effectiveAllowedTools.includes(toolId)
      ? effectiveAllowedTools.filter((item) => item !== toolId)
      : [...effectiveAllowedTools, toolId];
    updateToolPolicy(next);
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

        <FormField label={tl("Providers gerais disponíveis")}>
          <div className="flex flex-col gap-2.5">
            {providerOptions.map((provider) => (
              <ProviderChoiceCard
                key={provider.value}
                providerId={provider.value}
                title={provider.label}
                description={providerDescription(provider.value, provider.label)}
                selected={effectiveAllowedProviders.includes(provider.value)}
                onClick={() => toggleAllowedProvider(provider.value)}
              />
            ))}
          </div>
        </FormField>

        <FormField label={tl("Provider principal")}>
          <div className="flex flex-wrap gap-3">
            {effectiveAllowedProviders.map((providerId) => {
              const title =
                providerOptions.find((item) => item.value === providerId)?.label ?? providerId;
              return (
                <ProviderChoiceCard
                  key={providerId}
                  providerId={providerId}
                  title={title}
                  selected={effectiveDefaultProvider === providerId}
                  emphasized
                  badge={effectiveDefaultProvider === providerId ? tl("Principal") : undefined}
                  onClick={() => updateModelPolicy({ default_provider: providerId })}
                  className="min-w-[180px] flex-1"
                />
              );
            })}
          </div>
        </FormField>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(220px,0.7fr)_minmax(220px,0.7fr)]">
          <FormSelect
            label={tl("Modelo principal")}
            value={defaultModel}
            onChange={(event) =>
              updateModelPolicy({
                default_models: {
                  ...modelPolicy.default_models,
                  [effectiveDefaultProvider]: event.target.value,
                },
                tier_models: {
                  ...modelPolicy.tier_models,
                  [effectiveDefaultProvider]: {
                    ...(modelPolicy.tier_models[effectiveDefaultProvider] || {}),
                    medium: event.target.value,
                  },
                },
              })
            }
            options={defaultModelOptions}
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

        {modelFunctions.length > 0 ? (
          <SectionCollapsible title={tl("Modelos especializados por tipo de tarefa")}>
            <div className="flex flex-col gap-4 pt-2">
              {modelFunctions.map((functionItem) => {
                const functionId = String(functionItem.id || "");
                const options = (functionalModelCatalog[functionId] || []).map((item) => ({
                  value: `${String(item.provider_id)}:${String(item.model_id)}`,
                  label: `${String(item.provider_title || item.provider_id)} · ${String(item.title || item.model_id)}`,
                }));
                const currentSelection = modelPolicy.functional_defaults[functionId];
                const value =
                  currentSelection?.provider_id && currentSelection?.model_id
                    ? `${currentSelection.provider_id}:${currentSelection.model_id}`
                    : "";
                return (
                  <FormSelect
                    key={functionId}
                    label={String(functionItem.title || functionId)}
                    value={value}
                    onChange={(event) => {
                      const raw = event.target.value;
                      const nextDefaults = { ...modelPolicy.functional_defaults };
                      if (!raw) {
                        delete nextDefaults[functionId];
                      } else {
                        const [providerId, ...modelParts] = raw.split(":");
                        nextDefaults[functionId] = {
                          provider_id: providerId,
                          model_id: modelParts.join(":"),
                        };
                      }
                      updateModelPolicy({ functional_defaults: nextDefaults });
                    }}
                    options={[
                      { value: "", label: tl("Herdar do modelo principal") },
                      ...options.map((option) => {
                        const [providerId] = option.value.split(":");
                        const providerLabel = String(providerEntries[providerId]?.title || providerId);
                        const modelLabel = option.label.split(" · ").slice(-1)[0] || option.label;
                        return {
                          ...option,
                          label: modelLabel,
                          description: option.value.split(":").slice(1).join(":"),
                          group: providerLabel,
                          icon: (
                            <ProviderLogo
                              providerId={providerId}
                              active
                              size="sm"
                            />
                          ),
                        };
                      }),
                    ]}
                  />
                );
              })}
            </div>
          </SectionCollapsible>
        ) : null}
      </PolicyCard>

      <PolicyCard
        title={tl("Tools permitidas")}
        description={toolsSummaryLabel}
        icon={Wrench}
      >
        <div className="flex flex-col gap-3">
          {availableTools.map((tool) => (
            <ToolChoiceCard
              key={tool.value}
              title={tool.label}
              description={tool.description}
              selected={effectiveAllowedTools.includes(tool.value)}
              onClick={() => toggleAllowedTool(tool.value)}
            />
          ))}
        </div>
      </PolicyCard>

      <PolicyCard
        title={tl("Voz")}
        description={voiceModeLabel}
        icon={Volume2}
      >
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,220px)_minmax(0,1fr)_minmax(0,1fr)]">
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
          <FormInput
            label={tl("Duração alvo")}
            value={voicePolicy.duration_target}
            onChange={(event) => updateVoicePolicy({ duration_target: event.target.value })}
            placeholder={tl("Ex: 30-45s")}
          />
        </div>

        <MarkdownEditorField
          label={tl("Prompt de voz")}
          value={state.documents.voice_prompt_md ?? ""}
          onChange={(value) => updateDocument("voice_prompt_md", value)}
          minHeight="220px"
        />
      </PolicyCard>

      <PolicyCard
        title={tl("Imagem")}
        description={imageModeLabel}
        icon={ImageIcon}
      >
        <FormSelect
          label={tl("Comportamento padrão")}
          value={imagePolicy.fallback_behavior}
          onChange={(event) => updateImagePolicy({ fallback_behavior: event.target.value })}
          options={[
            { value: "describe", label: tl("Descrever e analisar") },
            { value: "summarize", label: tl("Resumir visualmente") },
            { value: "strict", label: tl("Ser conservador") },
          ]}
        />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <TagInputField
            label={tl("O que analisar primeiro")}
            values={imagePolicy.analysis_priorities}
            onChange={(values) => updateImagePolicy({ analysis_priorities: values })}
            placeholder={tl("Ex: texto, contexto, alertas")}
          />

          <TagInputField
            label={tl("Limites de segurança")}
            values={imagePolicy.safety_notes}
            onChange={(values) => updateImagePolicy({ safety_notes: values })}
            placeholder={tl("Ex: evitar inferir identidade")}
          />
        </div>

        <MarkdownEditorField
          label={tl("Prompt de imagem")}
          value={state.documents.image_prompt_md ?? ""}
          onChange={(value) => updateDocument("image_prompt_md", value)}
          minHeight="220px"
        />
      </PolicyCard>

      {developerMode ? (
        <SectionCollapsible title={tl("JSON avançado")}>
          <div className="flex flex-col gap-6 pt-2">
            <JsonEditorField
              label={tl("Política de modelo (JSON)")}
              description={tl("Contrato canônico que o runtime realmente materializa.")}
              value={state.modelPolicyJson}
              onChange={(value) => updateAgentSpecField("modelPolicyJson", value)}
            />
            <JsonEditorField
              label={tl("Política de tools (JSON)")}
              description={tl("Subset efetivo do catálogo de tools do core.")}
              value={state.toolPolicyJson}
              onChange={(value) => updateAgentSpecField("toolPolicyJson", value)}
            />
            <JsonEditorField
              label={tl("Política de voz (JSON)")}
              description={tl("Override avançado de voz e TTS.")}
              value={state.voicePolicyJson}
              onChange={(value) => updateAgentSpecField("voicePolicyJson", value)}
            />
            <JsonEditorField
              label={tl("Política de imagem (JSON)")}
              description={tl("Override avançado para análise visual.")}
              value={state.imageAnalysisPolicyJson}
              onChange={(value) => updateAgentSpecField("imageAnalysisPolicyJson", value)}
            />
          </div>
        </SectionCollapsible>
      ) : null}
    </div>
  );
}
