"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Pencil, X } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { ActionButton } from "@/components/ui/action-button";
import { AnimatedColorPicker } from "@/components/control-plane/shared/animated-color-picker";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { ModelSelector } from "@/components/control-plane/shared/model-selector";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import {
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import type {
  ControlPlaneCoreProviders,
  GeneralSystemSettings,
  GeneralSystemSettingsCatalogProvider,
  GeneralSystemSettingsProviderConnection,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";
import {
  validateColor,
  hexToRgb,
  componentsToRgbString,
} from "@/lib/control-plane-editor";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

function generateBotId(name: string): string {
  return name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/* ------------------------------------------------------------------ */
/*  Provider / model helpers                                           */
/* ------------------------------------------------------------------ */

type ProviderOption = { value: string; label: string };
type WizardSelectOption = { value: string; label: string };
type ProviderCatalogMap = Record<string, Record<string, unknown>>;

const EMPTY_SELECT_VALUE = "__empty__";

function prettifyModelId(modelId: string): string {
  if (!modelId) return "";
  return modelId
    .replace(/:latest$/i, "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .replace(/\bGpt\b/g, "GPT")
    .replace(/\bLlama\b/g, "Llama")
    .replace(/\bQwen\b/g, "Qwen");
}

function buildProviderCatalogMap(
  coreProviders: ControlPlaneCoreProviders,
): ProviderCatalogMap {
  return Object.fromEntries(
    Object.entries(coreProviders.providers ?? {}).map(([providerId, payload]) => [
      providerId,
      payload ?? {},
    ]),
  );
}

function getConnectedGeneralProviderOptions(
  coreProviders: ControlPlaneCoreProviders,
  generalSettings: GeneralSystemSettings | null | undefined,
): ProviderOption[] {
  if (!generalSettings) {
    const providerEntries = Object.entries(coreProviders.providers ?? {});
    return providerEntries
      .filter(([, payload]) => String(payload.category || "general") === "general")
      .filter(([providerId, payload]) => {
        if (
          Array.isArray(coreProviders.enabled_providers) &&
          coreProviders.enabled_providers.length > 0
        ) {
          return coreProviders.enabled_providers.map(String).includes(providerId);
        }
        return Boolean(payload.enabled);
      })
      .map(([providerId, payload]) => ({
        value: providerId,
        label: String(payload.title || payload.vendor || providerId),
      }));
  }

  const connections = generalSettings.values.provider_connections || {};
  return generalSettings.catalogs.providers
    .filter((provider) => provider.show_in_settings !== false)
    .filter((provider) => String(provider.category || "general") === "general")
    .filter((provider) => isConnectedGeneralProvider(provider, connections[provider.id]))
    .map((provider) => ({
      value: String(provider.id),
      label: String(provider.title || provider.vendor || provider.id),
    }));
}

function isConnectedGeneralProvider(
  provider: GeneralSystemSettingsCatalogProvider,
  connection?: GeneralSystemSettingsProviderConnection,
): boolean {
  if (provider.connection_managed === false) {
    return Boolean(provider.command_present);
  }
  return Boolean(connection?.verified);
}

function getProviderModels(
  coreProviders: ControlPlaneCoreProviders,
  generalSettings: GeneralSystemSettings | null | undefined,
  provider: string,
): ProviderOption[] {
  if (!provider) return [];

  const catalogModels =
    generalSettings?.catalogs.functional_model_catalog?.general?.filter(
      (item) => String(item.provider_id) === provider,
    ) ?? [];

  if (catalogModels.length > 0) {
    return catalogModels.map((item) => ({
      value: String(item.model_id),
      label: String(item.title || prettifyModelId(String(item.model_id))),
    }));
  }

  const payload = coreProviders.providers?.[provider] ?? {};
  const models = Array.isArray(payload.available_models)
    ? payload.available_models.map(String)
    : [];
  if (models.length === 0 && payload.default_model) {
    models.push(String(payload.default_model));
  }
  return models.map((modelId) => ({
    value: modelId,
    label: prettifyModelId(modelId),
  }));
}

function WizardSelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: WizardSelectOption[];
  placeholder: string;
  disabled?: boolean;
}) {
  const supportsEmptyOption = options.some((option) => option.value === "");
  const selectValue =
    value || supportsEmptyOption
      ? value || EMPTY_SELECT_VALUE
      : undefined;

  return (
    <div>
      <label className="eyebrow mb-1.5 block">{label}</label>
      <Select
        value={selectValue}
        onValueChange={(nextValue) =>
          onChange(nextValue === EMPTY_SELECT_VALUE ? "" : nextValue)
        }
        disabled={disabled}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent sideOffset={6}>
          {options.map((option) => (
            <SelectItem
              key={option.value || EMPTY_SELECT_VALUE}
              value={option.value || EMPTY_SELECT_VALUE}
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step indicator                                                     */
/* ------------------------------------------------------------------ */

const TOTAL_STEPS = 3;

function WizardStepIndicator({
  currentStep,
  labels,
}: {
  currentStep: number;
  labels: string[];
}) {
  return (
    <div className="wizard-step-indicator py-4">
      {labels.map((label, index) => (
        <div key={label} className="wizard-step-indicator__item">
          <span
            className={`wizard-step-indicator__circle ${
              index === currentStep
                ? "is-active"
                : index < currentStep
                  ? "is-complete"
                  : ""
            }`}
          >
            {index < currentStep ? (
              <Check size={13} strokeWidth={2.5} />
            ) : (
              index + 1
            )}
          </span>
          <span
            className={`wizard-step-indicator__label hidden sm:inline ${
              index === currentStep
                ? "is-active"
                : index < currentStep
                  ? "is-complete"
                  : ""
            }`}
          >
            {label}
          </span>
          {index < labels.length - 1 && (
            <span
              className={`wizard-step-indicator__connector ${
                index < currentStep ? "is-complete" : ""
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Slide animation                                                    */
/* ------------------------------------------------------------------ */

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 200 : -200,
    opacity: 0,
  }),
  center: { x: 0, opacity: 1 },
  exit: (direction: number) => ({
    x: direction > 0 ? -200 : 200,
    opacity: 0,
  }),
};

/* ------------------------------------------------------------------ */
/*  BotCreateWizard                                                    */
/* ------------------------------------------------------------------ */

interface BotCreateWizardProps {
  open: boolean;
  onClose: () => void;
  coreProviders: ControlPlaneCoreProviders;
  generalSettings?: GeneralSystemSettings | null;
  workspaces: ControlPlaneWorkspaceTree;
  suggestedHealthPort: number;
  initialWorkspaceId?: string;
  initialSquadId?: string;
}

export function BotCreateWizard({
  open,
  onClose,
  coreProviders,
  generalSettings = null,
  workspaces,
  suggestedHealthPort,
  initialWorkspaceId = "",
  initialSquadId = "",
}: BotCreateWizardProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const { t, tl } = useAppI18n();

  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);

  // Step 0: Identity
  const [displayName, setDisplayName] = useState("");
  const [color, setColor] = useState("#7A8799");
  const [botIdManual, setBotIdManual] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [editingId, setEditingId] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(initialWorkspaceId);
  const [squadId, setSquadId] = useState(initialSquadId);

  // Step 1: Prompt
  const [systemPrompt, setSystemPrompt] = useState("");

  // Step 2: Model
  const providerOptions = useMemo(
    () => getConnectedGeneralProviderOptions(coreProviders, generalSettings),
    [coreProviders, generalSettings],
  );
  const initialProvider = providerOptions[0]?.value || "";
  const [provider, setProvider] = useState(initialProvider);
  const [model, setModel] = useState("");
  const providerCatalog = useMemo(
    () => buildProviderCatalogMap(coreProviders),
    [coreProviders],
  );

  const [submitting, setSubmitting] = useState(false);

  // Derived values
  const botId = idEdited ? botIdManual : generateBotId(displayName);
  const namespace = botId.toLowerCase().replace(/[^a-z0-9]+/g, "_");

  const colorRgb = useMemo(() => {
    if (!validateColor(color)) return "";
    const rgb = hexToRgb(color);
    return rgb ? componentsToRgbString(rgb.r, rgb.g, rgb.b) : "";
  }, [color]);

  const currentModels = useMemo(
    () =>
      getProviderModels(
        coreProviders,
        generalSettings,
        provider || initialProvider,
      ),
    [coreProviders, generalSettings, initialProvider, provider],
  );

  const providerLabel = useMemo(
    () =>
      providerOptions.find((option) => option.value === provider)?.label ??
      providerOptions[0]?.label ??
      "",
    [provider, providerOptions],
  );

  const modelLabel = useMemo(
    () =>
      currentModels.find((option) => option.value === model)?.label ?? model ?? "",
    [currentModels, model],
  );

  const promptPlaceholder = t("controlPlane.botCreate.promptPlaceholder", {
    defaultValue:
      "You are an assistant specialized in...\n\nYour goal is to help users with...\n\nRules:\n- Be clear and objective\n- Always respond in English",
  });

  const workspaceOptions = useMemo(
    () => [
      { value: "", label: tl("Sem workspace") },
      ...workspaces.items.map((item) => ({ value: item.id, label: item.name })),
    ],
    [tl, workspaces.items],
  );

  const selectedWorkspace = useMemo(
    () => workspaces.items.find((item) => item.id === workspaceId) ?? null,
    [workspaceId, workspaces.items],
  );

  const squadOptions = useMemo(
    () => [
      { value: "", label: tl("Sem squad") },
      ...(selectedWorkspace?.squads.map((item) => ({
        value: item.id,
        label: item.name,
      })) ?? []),
    ],
    [selectedWorkspace, tl],
  );

  const stepLabels = useMemo(
    () => [tl("Identidade"), tl("Prompt"), tl("Modelo")],
    [tl],
  );

  // Sync provider
  useEffect(() => {
    if (!provider || !providerOptions.some((option) => option.value === provider)) {
      setProvider(initialProvider);
    }
  }, [initialProvider, provider, providerOptions]);

  // Sync initial workspace/squad when modal opens
  useEffect(() => {
    if (!open) return;
    setWorkspaceId(initialWorkspaceId);
    setSquadId(initialSquadId);
  }, [initialSquadId, initialWorkspaceId, open]);

  // Auto-select first model when provider changes
  useEffect(() => {
    const nextModel = currentModels[0]?.value || "";
    if (!model || !currentModels.some((item) => item.value === model)) {
      setModel(nextModel);
    }
  }, [currentModels, model]);

  function goNext() {
    setDirection(1);
    setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  }

  function goBack() {
    setDirection(-1);
    setStep((s) => Math.max(s - 1, 0));
  }

  const resetAndClose = useCallback(() => {
    setStep(0);
    setDirection(1);
    setDisplayName("");
    setColor("#7A8799");
    setBotIdManual("");
    setIdEdited(false);
    setEditingId(false);
    setWorkspaceId(initialWorkspaceId);
    setSquadId(initialSquadId);
    setSystemPrompt("");
    setProvider(initialProvider);
    setModel(
      getProviderModels(coreProviders, generalSettings, initialProvider)[0]
        ?.value || "",
    );
    setSubmitting(false);
    onClose();
  }, [
    coreProviders,
    generalSettings,
    initialProvider,
    initialSquadId,
    initialWorkspaceId,
    onClose,
  ]);

  useBodyScrollLock(open);
  useEscapeToClose(open, resetAndClose);

  async function handleCreate() {
    if (!botId.trim()) {
      showToast(tl("ID do agente e obrigatorio."), "error");
      return;
    }
    if (!provider.trim() || !model.trim()) {
      showToast(
        tl("Escolha um provider e um modelo habilitados pelo core."),
        "error",
      );
      return;
    }

    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        id: botId,
        display_name: displayName.trim() || botId.replace(/_/g, " "),
        status: "paused",
        storage_namespace: namespace,
        appearance: { label: displayName.trim(), color, color_rgb: colorRgb },
        runtime_endpoint: {
          health_port: suggestedHealthPort,
          health_url: `http://127.0.0.1:${suggestedHealthPort}/health`,
          runtime_base_url: `http://127.0.0.1:${suggestedHealthPort}`,
        },
        organization: {
          workspace_id: workspaceId || null,
          squad_id: workspaceId ? squadId || null : null,
        },
      };

      await requestJson("/api/control-plane/agents", {
        method: "POST",
        body: JSON.stringify(body),
      });

      // Save system prompt if provided
      if (systemPrompt.trim()) {
        try {
          await requestJson(
            `/api/control-plane/agents/${botId}/documents/system_prompt_md`,
            {
              method: "PUT",
              body: JSON.stringify({ content: systemPrompt.trim() }),
            },
          );
        } catch {
          /* Non-critical */
        }
      }

      // Save model config
      try {
        await requestJson(`/api/control-plane/agents/${botId}/agent-spec`, {
          method: "PUT",
          body: JSON.stringify({
            model_policy: {
              allowed_providers: provider ? [provider] : [],
              default_provider: provider,
              fallback_order: provider ? [provider] : [],
              available_models_by_provider: provider
                ? { [provider]: currentModels.map((item) => item.value) }
                : {},
              default_models: provider && model ? { [provider]: model } : {},
              tier_models:
                provider && model ? { [provider]: { medium: model } } : {},
            },
          }),
        });
      } catch {
        /* Non-critical */
      }

      showToast(
        tl('Agente "{{name}}" criado!', {
          name: displayName.trim() || botId,
        }),
        "success",
      );
      router.push(`/control-plane/bots/${botId}`);
      resetAndClose();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao criar agente."),
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const canProceedStep0 = displayName.trim().length > 0 && botId.length > 0;

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={resetAndClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={tl("Novo agente")}
          className="app-modal-panel agent-board-dialog agent-board-dialog--wizard relative flex w-full max-w-3xl flex-col overflow-hidden"
          onClick={(event) => event.stopPropagation()}
        >
          {/* Close button */}
          <button
            type="button"
            className="app-surface-close"
            onClick={resetAndClose}
            aria-label={tl("Fechar")}
          >
            <X className="h-4 w-4" />
          </button>

          {/* Header */}
          <div className="px-6 pb-0 pt-5 pr-14">
            <h3 className="text-[1.25rem] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
              {tl("Novo agente")}
            </h3>
          </div>

          {/* Step indicator */}
          <WizardStepIndicator
            currentStep={step}
            labels={stepLabels}
          />

          {/* Step content */}
          <div className="relative flex min-h-[340px] flex-1 flex-col px-6">
            <AnimatePresence mode="wait" custom={direction}>
              {/* ---- Step 0: Identity ---- */}
              {step === 0 && (
                <motion.div
                  key="step-0"
                  custom={direction}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                  className="space-y-4"
                >
                  {/* Name + Avatar row */}
                  <div className="flex items-start gap-4">
                    <BotAgentGlyph
                      botId={botId || "PREVIEW"}
                      color={color}
                      shape="swatch"
                      className="h-14 w-14 shrink-0 rounded-[0.72rem] bot-swatch--animated"
                    />
                    <div className="flex-1 min-w-0">
                      <label className="eyebrow mb-1.5 block">
                        {tl("Nome do agente")}
                      </label>
                      <input
                        type="text"
                        className="field-shell w-full px-4 py-3 text-sm"
                        placeholder={tl("Ex: Assistente de Vendas")}
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        autoFocus
                      />
                    </div>
                  </div>

                  {/* ID display */}
                  <div className="wizard-id-display">
                    <span>ID:</span>
                    {editingId ? (
                      <input
                        type="text"
                        className="field-shell px-2 py-1 font-mono text-xs uppercase"
                        style={{ width: Math.max(120, botId.length * 10) }}
                        value={botId}
                        onChange={(e) => {
                          setIdEdited(true);
                          setBotIdManual(e.target.value.toUpperCase());
                        }}
                        onBlur={() => setEditingId(false)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") setEditingId(false);
                        }}
                        autoFocus
                      />
                    ) : (
                      <>
                        <span>{botId || "—"}</span>
                        <button
                          type="button"
                          onClick={() => setEditingId(true)}
                          aria-label={tl("Editar ID")}
                        >
                          <Pencil size={11} />
                        </button>
                      </>
                    )}
                  </div>

                  {/* Color */}
                  <AnimatedColorPicker
                    label={tl("Cor")}
                    value={color}
                    onChange={setColor}
                  />

                  {/* Workspace + Squad */}
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <WizardSelectField
                      label={tl("Workspace")}
                      value={workspaceId}
                      onChange={(nextWorkspaceId) => {
                        setWorkspaceId(nextWorkspaceId);
                        const nextWorkspace = workspaces.items.find(
                          (item) => item.id === nextWorkspaceId,
                        );
                        const squadStillValid =
                          nextWorkspace?.squads.some(
                            (item) => item.id === squadId,
                          ) ?? false;
                        if (!nextWorkspaceId || !squadStillValid) {
                          setSquadId("");
                        }
                      }}
                      options={workspaceOptions}
                      placeholder={tl("Selecionar workspace")}
                    />
                    <WizardSelectField
                      label={tl("Squad")}
                      value={squadId}
                      onChange={setSquadId}
                      options={squadOptions}
                      placeholder={
                        workspaceId
                          ? tl("Selecionar squad")
                          : tl("Selecione um workspace primeiro")
                      }
                      disabled={!workspaceId}
                    />
                  </div>
                </motion.div>
              )}

              {/* ---- Step 1: Prompt ---- */}
              {step === 1 && (
                <motion.div
                  key="step-1"
                  custom={direction}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                  className="wizard-prompt-step"
                >
                  <div className="mb-3">
                    <p className="eyebrow mb-1">
                      {tl("System prompt")}
                    </p>
                    <p className="text-xs leading-5 text-[var(--text-quaternary)]">
                      {tl("Defina quem o agente e — personalidade, regras e capacidades.")}
                    </p>
                  </div>
                  <MarkdownEditorField
                    value={systemPrompt}
                    onChange={setSystemPrompt}
                    placeholder={promptPlaceholder}
                    hideFieldHeader
                    minHeight="260px"
                    textareaAriaLabel={tl("System prompt do agente")}
                    className="flex-1"
                  />
                </motion.div>
              )}

              {/* ---- Step 2: Model & Create ---- */}
              {step === 2 && (
                <motion.div
                  key="step-2"
                  custom={direction}
                  variants={slideVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                  className="space-y-5"
                >
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <WizardSelectField
                      label={tl("Provider")}
                      value={provider}
                      onChange={(nextProvider) => {
                        setProvider(nextProvider);
                        setModel(
                          getProviderModels(
                            coreProviders,
                            generalSettings,
                            nextProvider,
                          )[0]?.value || "",
                        );
                      }}
                      options={providerOptions}
                      placeholder={tl("Selecione um provider conectado")}
                      disabled={providerOptions.length === 0}
                    />

                    <ModelSelector
                      label={tl("Modelo")}
                      description={
                        provider
                          ? tl("Escolha o modelo principal do provider selecionado.")
                          : tl("Selecione primeiro um provider conectado.")
                      }
                      value={provider && model ? `${provider}:${model}` : ""}
                      onChange={(combined) => {
                        const [providerId, ...modelParts] = combined.split(":");
                        setProvider(providerId);
                        setModel(modelParts.join(":"));
                      }}
                      providers={providerCatalog}
                      enabledProviders={provider ? [provider] : []}
                      functionalCatalog={
                        generalSettings?.catalogs.functional_model_catalog
                      }
                      functionId="general"
                    />
                  </div>

                  {providerOptions.length === 0 ? (
                    <div className="rounded-[1.2rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4 text-sm leading-6 text-[var(--text-secondary)]">
                      {tl(
                        "Nenhum provider generativo conectado foi encontrado. Conecte OpenAI, Anthropic, Gemini, Ollama ou outro LLM generativo nas configuracoes do sistema para concluir a criacao.",
                      )}
                    </div>
                  ) : null}

                  {/* Summary card */}
                  <div className="agent-board-review space-y-4 p-5">
                    <div className="flex items-start gap-3">
                      <BotAgentGlyph
                        botId={botId || "PREVIEW"}
                        color={color}
                        shape="swatch"
                        className="h-12 w-12 rounded-[0.72rem]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate text-base font-semibold text-[var(--text-primary)]">
                            {displayName.trim() || botId.replace(/_/g, " ")}
                          </p>
                          <span className="chip text-[10px]">
                            {tl("Pausado")}
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-[10px] tracking-[0.18em] text-[var(--text-quaternary)]">
                          {botId}
                        </p>
                        <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--text-secondary)]">
                          {systemPrompt.trim()
                            ? systemPrompt.trim()
                            : tl(
                                "Sem system prompt definido. Voce podera configurar as instrucoes do agente logo apos a criacao.",
                              )}
                        </p>
                      </div>
                    </div>

                    <div className="grid gap-3 border-t border-[var(--border-subtle)] pt-4 md:grid-cols-2">
                      <div className="rounded-[1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
                        <p className="eyebrow mb-1">{tl("Workspace")}</p>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {selectedWorkspace?.name ?? tl("Sem workspace")}
                        </p>
                      </div>
                      <div className="rounded-[1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
                        <p className="eyebrow mb-1">{tl("Squad")}</p>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {selectedWorkspace
                            ? (selectedWorkspace.squads.find(
                                (item) => item.id === squadId,
                              )?.name ?? tl("Sem squad"))
                            : "—"}
                        </p>
                      </div>
                      <div className="rounded-[1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
                        <p className="eyebrow mb-1">{tl("Provider")}</p>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {providerLabel || tl("Nao definido")}
                        </p>
                      </div>
                      <div className="rounded-[1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
                        <p className="eyebrow mb-1">{tl("Modelo")}</p>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {modelLabel || tl("Nao definido")}
                        </p>
                      </div>
                    </div>

                    <div className="rounded-[1rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
                      <p className="eyebrow mb-1">{tl("Resumo operacional")}</p>
                      <p className="text-sm leading-6 text-[var(--text-secondary)]">
                        {tl(
                          "O agente sera criado em pausa, com identidade visual, posicionamento organizacional e stack principal definidos. Depois disso, voce podera aprofundar instrucoes, ferramentas e politicas com mais granularidade.",
                        )}
                      </p>
                    </div>
                  </div>

                  <p className="text-[11px] text-[var(--text-quaternary)]">
                    {tl("Voce podera ajustar todas as configuracoes apos a criacao.")}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Footer */}
          <div className="mt-auto flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
            <div>
              {step > 0 ? (
                <ActionButton
                  type="button"
                  onClick={goBack}
                  disabled={submitting}
                >
                  {tl("Voltar")}
                </ActionButton>
              ) : null}
            </div>

            <div className="flex items-center gap-2">
              {step === 1 && !systemPrompt.trim() ? (
                <ActionButton type="button" onClick={goNext}>
                  {tl("Pular")}
                </ActionButton>
              ) : null}

              {step < TOTAL_STEPS - 1 ? (
                <ActionButton
                  type="button"
                  variant="primary"
                  onClick={goNext}
                  disabled={step === 0 && !canProceedStep0}
                >
                  {tl("Continuar")}
                </ActionButton>
              ) : (
                <ActionButton
                  type="button"
                  variant="primary"
                  loading={submitting}
                  onClick={handleCreate}
                  disabled={
                    submitting ||
                    !botId.trim() ||
                    !provider.trim() ||
                    !model.trim()
                  }
                >
                  {submitting ? tl("Criando...") : tl("Criar agente")}
                </ActionButton>
              )}
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
