"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { ActionButton } from "@/components/ui/action-button";
import { AnimatedColorPicker } from "@/components/control-plane/shared/animated-color-picker";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import {
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { agentBoardAssets } from "@/lib/agent-board-assets";
import type {
  ControlPlaneCoreProviders,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";
import {
  validateColor,
  hexToRgb,
  componentsToRgbString,
} from "@/lib/control-plane-editor";

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

const TOTAL_STEPS = 3;

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

type ProviderOption = { value: string; label: string };

function getEnabledProviderIds(
  coreProviders: ControlPlaneCoreProviders,
): string[] {
  if (
    Array.isArray(coreProviders.enabled_providers) &&
    coreProviders.enabled_providers.length > 0
  ) {
    return coreProviders.enabled_providers.map(String);
  }
  return Object.entries(coreProviders.providers ?? {})
    .filter(([, payload]) => Boolean(payload.enabled))
    .map(([provider]) => provider);
}

function getProviderOptions(
  coreProviders: ControlPlaneCoreProviders,
): ProviderOption[] {
  return getEnabledProviderIds(coreProviders).map((provider) => {
    const payload = coreProviders.providers?.[provider] ?? {};
    return {
      value: provider,
      label: String(payload.title || payload.vendor || provider),
    };
  });
}

function getProviderModels(
  coreProviders: ControlPlaneCoreProviders,
  provider: string,
): ProviderOption[] {
  const payload = coreProviders.providers?.[provider] ?? {};
  const models = Array.isArray(payload.available_models)
    ? payload.available_models.map(String)
    : [];
  if (models.length === 0 && payload.default_model) {
    models.push(String(payload.default_model));
  }
  return models.map((model) => ({ value: model, label: model }));
}

interface BotCreateWizardProps {
  open: boolean;
  onClose: () => void;
  coreProviders: ControlPlaneCoreProviders;
  workspaces: ControlPlaneWorkspaceTree;
  suggestedHealthPort: number;
  initialWorkspaceId?: string;
  initialSquadId?: string;
}

export function BotCreateWizard({
  open,
  onClose,
  coreProviders,
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

  // Step 1: Identity
  const [displayName, setDisplayName] = useState("");
  const [color, setColor] = useState("#7A8799");
  const [botIdManual, setBotIdManual] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(initialWorkspaceId);
  const [squadId, setSquadId] = useState(initialSquadId);

  // Step 2: Instructions + Model
  const [systemPrompt, setSystemPrompt] = useState("");
  const providerOptions = useMemo(
    () => getProviderOptions(coreProviders),
    [coreProviders],
  );
  const initialProvider = providerOptions[0]?.value || "";
  const [provider, setProvider] = useState(initialProvider);
  const [model, setModel] = useState("");

  const [submitting, setSubmitting] = useState(false);

  const botId = idEdited ? botIdManual : generateBotId(displayName);
  const namespace = botId.toLowerCase().replace(/[^a-z0-9]+/g, "_");

  const colorRgb = useMemo(() => {
    if (!validateColor(color)) return "";
    const rgb = hexToRgb(color);
    return rgb ? componentsToRgbString(rgb.r, rgb.g, rgb.b) : "";
  }, [color]);

  const currentModels = useMemo(
    () => getProviderModels(coreProviders, provider || initialProvider),
    [coreProviders, initialProvider, provider],
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

  useEffect(() => {
    if (!provider && initialProvider) {
      setProvider(initialProvider);
    }
  }, [initialProvider, provider]);

  useEffect(() => {
    if (!open) return;
    setWorkspaceId(initialWorkspaceId);
    setSquadId(initialSquadId);
  }, [initialSquadId, initialWorkspaceId, open]);

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
    setWorkspaceId(initialWorkspaceId);
    setSquadId(initialSquadId);
    setSystemPrompt("");
    setProvider(initialProvider);
    setModel(getProviderModels(coreProviders, initialProvider)[0]?.value || "");
    setSubmitting(false);
    onClose();
  }, [
    coreProviders,
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

      showToast(tl('Agente "{{name}}" criado!', { name: displayName.trim() || botId }), "success");
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
  const stepMeta = [
    {
      eyebrow: tl("Identidade"),
      title: tl("Novo agente"),
      description: tl("Defina nome, aparencia e organizacao base do agente."),
      asset: agentBoardAssets.workspaceFolder,
    },
    {
      eyebrow: tl("Configuracao"),
      title: tl("Modelo e instrucoes"),
      description: tl("Escolha o provider principal e as instrucoes iniciais do agente."),
      asset: agentBoardAssets.signalStack,
    },
    {
      eyebrow: tl("Revisao"),
      title: tl("Conferencia final"),
      description: tl("Revise os dados principais antes de publicar o novo agente no catalogo."),
      asset: agentBoardAssets.boardDoc,
    },
  ] as const;

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <>
      <motion.div
        className="agent-board-dialog-backdrop z-[70]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={resetAndClose}
      />

      <motion.div
        className="app-modal-frame z-[80] p-4"
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.97 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      >
        <div
          className="agent-board-dialog agent-board-dialog--wizard relative z-10 w-full max-w-5xl overflow-hidden"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="grid min-h-[620px] lg:grid-cols-[280px_minmax(0,1fr)]">
            <aside className="agent-board-wizard__aside hidden lg:flex">
              <div className="space-y-6">
                <div className="agent-board-wizard__asset">
                  <Image
                    src={stepMeta[step].asset}
                    alt=""
                    width={72}
                    height={72}
                    className="h-[4.5rem] w-[4.5rem] opacity-90 invert"
                  />
                </div>

                <div className="space-y-2">
                  <p className="eyebrow">{stepMeta[step].eyebrow}</p>
                  <h3 className="text-[1.7rem] font-medium tracking-[-0.05em] text-[var(--text-primary)]">
                    {stepMeta[step].title}
                  </h3>
                  <p className="text-sm leading-6 text-[rgba(255,255,255,0.52)]">
                    {stepMeta[step].description}
                  </p>
                </div>

                <div className="space-y-3">
                  {stepMeta.map((item, index) => (
                    <div
                      key={item.title}
                      className={`agent-board-wizard__step ${step === index ? "is-active" : ""} ${
                        step > index ? "is-complete" : ""
                      }`}
                    >
                      <span className="agent-board-wizard__step-index">
                        {index + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium tracking-[-0.02em] text-[var(--text-primary)]">
                          {item.title}
                        </p>
                        <p className="text-xs text-[rgba(255,255,255,0.42)]">
                          {item.eyebrow}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="agent-board-wizard__hint">
                <p className="text-sm leading-6 text-[rgba(255,255,255,0.48)]">
                  {tl("O agente nasce pausado e pode ser refinado depois no editor, sem interromper a organizacao dos seus times.")}
                </p>
              </div>
            </aside>

            <div className="flex min-w-0 flex-col p-6 sm:p-8">
              <div className="flex items-start justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] pb-5">
                <div className="space-y-2">
                  <p className="eyebrow">{stepMeta[step].eyebrow}</p>
                  <h3 className="text-[1.55rem] font-medium tracking-[-0.05em] text-[var(--text-primary)] lg:hidden">
                    {stepMeta[step].title}
                  </h3>
                  <p className="hidden max-w-2xl text-sm leading-6 text-[rgba(255,255,255,0.5)] lg:block">
                    {stepMeta[step].description}
                  </p>
                </div>

                <button
                  type="button"
                  className="agent-board-inline-action"
                  onClick={resetAndClose}
                  aria-label={tl("Fechar")}
                >
                  {tl("Fechar")}
                </button>
              </div>

              <div className="mb-6 mt-5 flex items-center gap-2 lg:hidden">
                {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
                  <span
                    key={i}
                    className="h-1.5 rounded-full transition-all duration-300"
                    style={{
                      width: i === step ? 32 : 10,
                      background:
                        i === step
                          ? "rgba(255,255,255,0.92)"
                          : i < step
                            ? "rgba(255,255,255,0.48)"
                            : "rgba(255,255,255,0.12)",
                    }}
                  />
                ))}
              </div>

              <div className="relative min-h-[380px] flex-1">
                <AnimatePresence mode="wait" custom={direction}>
                  {/* Step 0: Identity */}
                  {step === 0 && (
                    <motion.div
                      key="step-0"
                      custom={direction}
                      variants={slideVariants}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <div className="mb-6 flex items-center justify-center">
                        <BotAgentGlyph
                          botId={botId || "PREVIEW"}
                          color={color}
                          className="h-[84px] w-[84px] bot-orb--animated"
                        />
                      </div>

                      <label className="eyebrow mb-1.5 block">
                        {tl("Nome do agente")}
                      </label>
                      <input
                        type="text"
                        className="field-shell mb-4 px-4 py-3 text-sm"
                        placeholder={tl("Ex: Assistente de Vendas")}
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        autoFocus
                      />

                      <AnimatedColorPicker
                        label={tl("Cor")}
                        value={color}
                        onChange={setColor}
                      />

                      <label className="eyebrow mb-1.5 block">{tl("ID")}</label>
                      <input
                        type="text"
                        className="field-shell font-mono text-sm uppercase px-3 py-2"
                        placeholder={tl("MEU_AGENTE")}
                        value={botId}
                        onChange={(e) => {
                          setIdEdited(true);
                          setBotIdManual(e.target.value.toUpperCase());
                        }}
                      />
                      <p className="text-[10px] text-[var(--text-quaternary)] mt-1">
                        {tl("Gerado automaticamente a partir do nome. Editavel.")}
                      </p>

                      <div className="grid grid-cols-1 gap-4 mt-4 md:grid-cols-2">
                        <div>
                          <label className="eyebrow mb-1.5 block">
                            {tl("Workspace")}
                          </label>
                          <select
                            value={workspaceId}
                            onChange={(event) => {
                              const nextWorkspaceId = event.target.value;
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
                            className="field-shell w-full px-3 py-2.5 text-sm text-[var(--text-primary)]"
                          >
                            {workspaceOptions.map((option) => (
                              <option
                                key={option.value || "__no_workspace__"}
                                value={option.value}
                              >
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="eyebrow mb-1.5 block">{tl("Squad")}</label>
                          <select
                            value={squadId}
                            onChange={(event) => setSquadId(event.target.value)}
                            className="field-shell w-full px-3 py-2.5 text-sm text-[var(--text-primary)]"
                            disabled={!workspaceId}
                          >
                            {squadOptions.map((option) => (
                              <option
                                key={option.value || "__no_squad__"}
                                value={option.value}
                              >
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {/* Step 1: Instructions + Model */}
                  {step === 1 && (
                    <motion.div
                      key="step-1"
                      custom={direction}
                      variants={slideVariants}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <label className="eyebrow mb-1.5 block">
                        {tl("Instrucoes do agente")}
                      </label>
                      <textarea
                        className="field-shell min-h-[120px] font-mono text-sm leading-relaxed mb-4 px-4 py-3"
                        placeholder={promptPlaceholder}
                        value={systemPrompt}
                        onChange={(e) => setSystemPrompt(e.target.value)}
                      />

                      <label className="eyebrow mb-1.5 block">{tl("Modelo")}</label>
                      <div className="agent-board-tabs mb-3">
                        {providerOptions.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={`agent-board-tab ${provider === option.value ? "is-active" : ""}`}
                            onClick={() => {
                              setProvider(option.value);
                              setModel(
                                getProviderModels(
                                  coreProviders,
                                  option.value,
                                )[0]?.value || "",
                              );
                            }}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                      <select
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        className="field-shell px-3 py-2.5 text-sm text-[var(--text-primary)]"
                      >
                        {currentModels.map((m) => (
                          <option key={m.value} value={m.value}>
                            {m.label}
                          </option>
                        ))}
                      </select>
                    </motion.div>
                  )}

                  {/* Step 2: Review */}
                  {step === 2 && (
                    <motion.div
                      key="step-2"
                      custom={direction}
                      variants={slideVariants}
                      initial="enter"
                      animate="center"
                      exit="exit"
                      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    >
                      <div className="agent-board-review space-y-4 p-5 sm:p-6">
                        <div className="flex items-center gap-4">
                          <BotAgentGlyph
                            botId={botId || "PREVIEW"}
                            color={color}
                            className="h-14 w-14"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-base font-semibold text-[var(--text-primary)] truncate">
                              {displayName.trim() || botId.replace(/_/g, " ")}
                            </p>
                            <p className="text-xs text-[var(--text-quaternary)] font-mono">
                              {botId}
                            </p>
                          </div>
                        </div>

                        <div className="text-sm space-y-2 pt-3 border-t border-[var(--border-subtle)]">
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Modelo")}</span>
                            <span className="font-mono text-[var(--text-secondary)]">
                              {currentModels.find((m) => m.value === model)
                                ?.label ?? model}
                            </span>
                          </div>
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Provedor")}</span>
                            <span className="text-[var(--text-secondary)]">
                              {providerOptions.find(
                                (item) => item.value === provider,
                              )?.label ?? provider}
                            </span>
                          </div>
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Workspace")}</span>
                            <span className="text-[var(--text-secondary)]">
                              {selectedWorkspace?.name ?? tl("Sem workspace")}
                            </span>
                          </div>
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Squad")}</span>
                            <span className="text-[var(--text-secondary)]">
                              {selectedWorkspace
                                ? (selectedWorkspace.squads.find(
                                    (item) => item.id === squadId,
                                  )?.name ?? tl("Sem squad"))
                                : "—"}
                            </span>
                          </div>
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Instrucoes")}</span>
                            <span className="text-[var(--text-secondary)]">
                              {systemPrompt.trim()
                                ? tl("Configuradas")
                                : tl("Nao definidas")}
                            </span>
                          </div>
                          <div className="flex justify-between text-[var(--text-tertiary)]">
                            <span>{tl("Status inicial")}</span>
                            <span className="chip text-[10px]">{tl("Pausado")}</span>
                          </div>
                        </div>

                        {systemPrompt.trim() && (
                          <div className="pt-3 border-t border-[var(--border-subtle)]">
                            <p className="text-[10px] text-[var(--text-quaternary)] mb-1">
                              {tl("Preview das instrucoes:")}
                            </p>
                            <p className="text-xs text-[var(--text-tertiary)] line-clamp-3 font-mono">
                              {systemPrompt.trim()}
                            </p>
                          </div>
                        )}
                      </div>

                      <p className="text-xs text-[var(--text-quaternary)] mt-3">
                        {tl("Voce podera ajustar todas as configuracoes apos a criacao.")}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="mt-6 flex items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-5">
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
                      onClick={goNext}
                      disabled={step === 0 && !canProceedStep0}
                    >
                      {tl("Continuar")}
                    </ActionButton>
                  ) : (
                    <ActionButton
                      type="button"
                      loading={submitting}
                      onClick={handleCreate}
                      disabled={submitting || !botId.trim()}
                    >
                      {submitting ? tl("Criando...") : tl("Criar agente")}
                    </ActionButton>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </>,
    document.body,
  );
}
