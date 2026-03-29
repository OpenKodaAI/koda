"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { ComponentType } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Cpu,
  Database,
  Fingerprint,
  KeyRound,
  Rocket,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { BotEditorProvider, useBotEditor } from "@/hooks/use-bot-editor";
import { useTabNavigation } from "@/hooks/use-tab-navigation";
import { cn } from "@/lib/utils";
import type {
  ControlPlaneBot,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";
import { TabConhecimento } from "./tabs/tab-conhecimento";
import { TabEscopo } from "./tabs/tab-escopo";
import { TabInstrucoes } from "./tabs/tab-instrucoes";
import { TabPerfil } from "./tabs/tab-perfil";
import { TabPublicacao } from "./tabs/tab-publicacao";
import { TabRecursos } from "./tabs/tab-recursos";

const STEP_KEYS = [
  "identidade",
  "comportamento",
  "recursos",
  "conhecimento",
  "escopo",
  "publicacao",
] as const;

type StepKey = (typeof STEP_KEYS)[number];

type StepDefinition = {
  key: StepKey;
  label: string;
  title: string;
  description: string;
  summary: string;
  icon: LucideIcon;
};

const STEP_DEFINITIONS: StepDefinition[] = [
  {
    key: "identidade",
    label: "Identidade",
    title: "Fundação do agente",
    description:
      "Defina nome, presença visual, workspace e o endereço base do runtime sem misturar isso com instruções comportamentais.",
    summary: "Quem é o agente e como ele aparece no catálogo.",
    icon: Fingerprint,
  },
  {
    key: "comportamento",
    label: "Comportamento",
    title: "Missão, regras e autonomia",
    description:
      "Organize missão, padrões de resposta, políticas e guardrails em uma etapa com mais espaço para escrita e governança real.",
    summary: "Objetivo, qualidade, regras duras e nível de autonomia.",
    icon: BrainCircuit,
  },
  {
    key: "recursos",
    label: "Recursos",
    title: "Modelo, tools e capacidades",
    description:
      "Escolha o envelope geral de raciocínio e as capabilities especializadas sem misturar providers gerais com mídia ou voz.",
    summary: "Envelope de modelos, subset de tools, voz e imagem.",
    icon: Cpu,
  },
  {
    key: "conhecimento",
    label: "Conhecimento",
    title: "Memória persistente e grounding",
    description:
      "Mantenha a política de memória, RAG e ativos de conhecimento em uma etapa própria, enquanto o knowledge graph e a recuperação híbrida permanecem autônomos no runtime.",
    summary: "Memória, RAG, assets, templates e skills.",
    icon: Database,
  },
  {
    key: "escopo",
    label: "Escopo",
    title: "Acesso a segredos e variáveis",
    description:
      "Conceda apenas os recursos necessários para o agente operar com segurança, sem espalhar grants e segredos em outras etapas.",
    summary: "Segredos, variáveis compartilhadas e local env.",
    icon: KeyRound,
  },
  {
    key: "publicacao",
    label: "Publicação",
    title: "Validação e runtime publicado",
    description:
      "Revise a composição final do agente, rode validações e publique sem sobrecarregar o restante do setup com detalhes operacionais.",
    summary: "Validação, prompt compilado, pipeline e publicação.",
    icon: Rocket,
  },
];

const STEP_COMPONENTS: Record<StepKey, ComponentType> = {
  identidade: TabPerfil,
  comportamento: TabInstrucoes,
  recursos: TabRecursos,
  conhecimento: TabConhecimento,
  escopo: TabEscopo,
  publicacao: TabPublicacao,
};

function dirtyForStep(step: StepKey, state: ReturnType<typeof useBotEditor>["state"]) {
  if (step === "identidade") return state.dirty.meta;
  if (step === "comportamento") return state.dirty.agentSpec || state.dirty.documents;
  if (step === "recursos") return state.dirty.agentSpec || state.dirty.documents;
  if (step === "conhecimento") {
    return state.dirty.collections || state.dirty.agentSpec || state.dirty.documents;
  }
  if (step === "escopo") return state.dirty.agentSpec;
  return false;
}

function EditorHeader({
  previousStep,
  nextStep,
  hasUnsavedChanges,
  onPrevious,
  onNext,
  onDiscard,
  onSave,
  isSaving,
  saveStatus,
}: {
  previousStep: StepDefinition | null;
  nextStep: StepDefinition | null;
  hasUnsavedChanges: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onDiscard: () => void;
  onSave: () => Promise<void>;
  isSaving: boolean;
  saveStatus: "idle" | "pending" | "success" | "error";
}) {
  const { state } = useBotEditor();
  const { tl } = useAppI18n();

  const botId = state.bot.id;

  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-2 lg:px-5 lg:py-2" {...tourAnchor("editor.header")}>
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[0.7rem]">
            <BotAgentGlyph
              botId={botId}
              color={state.color || "#8B8B93"}
              className="h-8 w-8 rounded-[0.7rem] bot-swatch--animated"
              active={state.status === "active"}
              variant="card"
              shape="swatch"
            />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <Link
                href="/control-plane"
                className="shrink-0 text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-secondary)]"
                {...tourAnchor("editor.back-link")}
              >
                {tl("Agentes")}
              </Link>
              <span className="text-[11px] text-[var(--text-quaternary)]">/</span>
              <span className="truncate text-[11px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
                {botId}
              </span>
            </div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2.5">
              <h1 className="truncate text-[1.28rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {state.displayName || botId}
              </h1>
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-2 xl:items-end">
          <div className="flex min-w-0 items-center gap-3 xl:justify-end">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={onPrevious}
                disabled={!previousStep}
                className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-transparent px-3.5 py-2 text-sm text-[var(--text-secondary)] shadow-none transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
                {...tourAnchor("editor.previous-step")}
              >
                <ArrowLeft size={15} />
                {tl("Voltar")}
              </button>
              <button
                type="button"
                onClick={onNext}
                className="inline-flex items-center gap-2 rounded-xl border border-[rgba(255,255,255,0.1)] bg-[rgba(255,255,255,0.03)] px-3.5 py-2 text-sm text-[var(--text-primary)] shadow-none transition-colors hover:border-[rgba(255,255,255,0.16)] hover:bg-[rgba(255,255,255,0.05)]"
                {...tourAnchor("editor.next-step")}
              >
                {nextStep ? tl("Avançar") : tl("Revisar publicação")}
                <ArrowRight size={15} />
              </button>
              {hasUnsavedChanges ? (
                <>
                  <span className="mx-1 hidden h-5 w-px bg-[var(--border-subtle)] lg:block" />
                  <button
                    type="button"
                    onClick={onDiscard}
                    className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-transparent px-3.5 py-2 text-sm text-[var(--text-secondary)] shadow-none transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                    {...tourAnchor("editor.discard")}
                  >
                    {tl("Descartar")}
                  </button>
                  <AsyncActionButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={onSave}
                    loading={isSaving}
                    loadingLabel={tl("Salvando")}
                    status={saveStatus}
                    className="shadow-none"
                    {...tourAnchor("editor.save")}
                  >
                    {tl("Salvar")}
                  </AsyncActionButton>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function ActiveStepRenderer({
  activeStep,
  direction,
}: {
  activeStep: StepKey;
  direction: number;
}) {
  const ActiveComponent = STEP_COMPONENTS[activeStep];
  if (!ActiveComponent) return null;

  return (
    <AnimatePresence mode="wait" custom={direction}>
      <motion.div
        key={activeStep}
        custom={direction}
        initial={{ x: direction > 0 ? 96 : -96, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: direction > 0 ? -96 : 96, opacity: 0 }}
        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        {...tourAnchor(`editor.step.${activeStep}`)}
      >
        <ActiveComponent />
      </motion.div>
    </AnimatePresence>
  );
}

function InnerShell() {
  const { state, persistDraft, discardDraft } = useBotEditor();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending, getStatus } = useAsyncAction();
  const { activeTab, setActiveTab } = useTabNavigation([...STEP_KEYS]);
  const [prevStepIndex, setPrevStepIndex] = useState(0);

  const currentStepIndex = Math.max(
    0,
    STEP_KEYS.indexOf(activeTab as StepKey),
  );
  const direction = currentStepIndex >= prevStepIndex ? 1 : -1;
  const activeStep = STEP_DEFINITIONS[currentStepIndex] ?? STEP_DEFINITIONS[0];
  const previousStep = currentStepIndex > 0 ? STEP_DEFINITIONS[currentStepIndex - 1] : null;
  const nextStep =
    currentStepIndex < STEP_DEFINITIONS.length - 1
      ? STEP_DEFINITIONS[currentStepIndex + 1]
      : null;

  const steps = useMemo(
    () =>
      STEP_DEFINITIONS.map((step, index) => ({
        ...step,
        index,
        dirty: dirtyForStep(step.key, state),
        completed: index < currentStepIndex && !dirtyForStep(step.key, state),
      })),
    [currentStepIndex, state],
  );
  const hasUnsavedChanges = Object.values(state.dirty).some(Boolean);

  function handleStepChange(step: StepKey) {
    setPrevStepIndex(currentStepIndex);
    setActiveTab(step);
  }

  async function handleSaveDraft() {
    await runAction(
      "save-editor",
      async () => {
        await persistDraft();
        router.refresh();
      },
      {
        successMessage: tl("Alterações salvas com sucesso."),
        errorMessage: tl("Erro ao salvar alterações."),
      },
    );
  }

  return (
    <div
      className="h-full min-h-0 w-full overflow-hidden"
      {...tourRoute("control-plane.editor")}
    >
      <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--surface-canvas)]">
        <EditorHeader
          previousStep={previousStep}
          nextStep={nextStep}
          hasUnsavedChanges={hasUnsavedChanges}
          onPrevious={() => previousStep && handleStepChange(previousStep.key)}
          onNext={() => handleStepChange(nextStep ? nextStep.key : "publicacao")}
          onDiscard={discardDraft}
          onSave={handleSaveDraft}
          isSaving={isPending("save-editor")}
          saveStatus={getStatus("save-editor")}
        />

        <div className="grid h-full min-h-0 flex-1 overflow-hidden lg:grid-cols-[182px_minmax(0,1fr)]">
          <aside className="h-full min-h-0 border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] lg:border-b-0 lg:border-r" {...tourAnchor("editor.step-rail")}>
            <div className="flex h-full flex-col px-2 py-3 lg:px-2.5 lg:py-4">
              <div className="mb-2 px-1.5">
                <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--text-quaternary)]">
                  {tl("Fluxo")}
                </span>
              </div>

              <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto pr-1">
                {steps.map((step) => {
                  const Icon = step.icon;
                  const isActive = step.key === activeStep.key;
                  const isCompleted = step.completed;
                  return (
                    <button
                      key={step.key}
                      type="button"
                      onClick={() => handleStepChange(step.key)}
                      aria-current={isActive ? "step" : undefined}
                      data-state={isActive ? "active" : isCompleted ? "completed" : "idle"}
                      {...tourAnchor(`editor.step.${step.key}`)}
                      className={cn(
                        "group relative flex min-h-[50px] shrink-0 items-center gap-2.5 rounded-[1rem] border px-2 py-2 text-left transition-colors duration-200",
                        isActive
                          ? "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.04)]"
                          : isCompleted
                            ? "border-transparent bg-transparent"
                          : "border-transparent bg-transparent",
                      )}
                    >
                      <span
                        className={cn(
                          "absolute left-0 top-1/2 h-6 w-px -translate-y-1/2 rounded-full transition-opacity",
                          isActive
                            ? "bg-[rgba(255,255,255,0.3)] opacity-100"
                            : isCompleted
                              ? "bg-[color-mix(in_srgb,var(--tone-success-border)_72%,transparent)] opacity-90"
                              : "opacity-0 group-hover:opacity-70 bg-[var(--border-subtle)]",
                        )}
                      />
                      <span
                        className={cn(
                          "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[0.9rem] border transition-colors",
                          isActive
                            ? "border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.06)] text-white"
                            : isCompleted
                              ? "border-[color-mix(in_srgb,var(--tone-success-border)_58%,transparent)] bg-[color-mix(in_srgb,var(--tone-success-bg)_38%,transparent)] text-[var(--tone-success-text)]"
                              : "border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] text-[var(--text-tertiary)]",
                        )}
                      >
                      {step.completed ? <CheckCircle2 size={16} /> : <Icon size={16} />}
                      </span>

                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span
                            className={cn(
                              "text-[10px] font-medium uppercase tracking-[0.18em]",
                              isCompleted
                                ? "text-[var(--tone-success-muted)]"
                                : "text-[var(--text-quaternary)]",
                            )}
                          >
                            {step.index + 1}
                          </span>
                          <span
                            className={cn(
                              "text-[0.95rem] font-medium tracking-[-0.02em]",
                              isCompleted
                                ? "text-[var(--text-primary)]"
                                : "text-[var(--text-primary)]",
                            )}
                          >
                            {tl(step.label)}
                          </span>
                          {step.dirty ? (
                            <span
                              className="inline-block h-2 w-2 shrink-0 rounded-full animate-pulse"
                              style={{ backgroundColor: "rgba(255,255,255,0.52)" }}
                              aria-label={tl("Alteracoes nao salvas")}
                            />
                          ) : null}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          <div className="relative flex h-full min-h-0 flex-col overflow-hidden" {...tourAnchor("editor.active-step")}>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 lg:px-8 lg:py-6">
              <ActiveStepRenderer activeStep={activeStep.key} direction={direction} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface BotEditorShellProps {
  bot: ControlPlaneBot;
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
}

export function BotEditorShell({
  bot,
  compiledPromptPayload,
  core,
  workspaces,
  systemSettings,
}: BotEditorShellProps) {
  return (
    <BotEditorProvider
      bot={bot}
      compiledPromptPayload={compiledPromptPayload}
      core={core}
      workspaces={workspaces}
      systemSettings={systemSettings}
    >
      <InnerShell />
    </BotEditorProvider>
  );
}
