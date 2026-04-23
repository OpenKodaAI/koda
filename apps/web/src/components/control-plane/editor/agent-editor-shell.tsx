"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import type { ComponentType } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  Cpu,
  Database,
  Fingerprint,
  KeyRound,
  Plug,
  Rocket,
  Wand2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { AgentEditorProvider, useAgentEditor } from "@/hooks/use-agent-editor";
import { useTabNavigation } from "@/hooks/use-tab-navigation";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";
import type {
  ControlPlaneAgent,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCoreIntegrations,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneExecutionPolicyPayload,
  ControlPlaneSystemSettings,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";
import { TabConhecimento } from "./tabs/tab-conhecimento";
import { TabIntegracoes } from "./tabs/tab-integracoes";
import { TabInstrucoes } from "./tabs/tab-instrucoes";
import { TabPerfil } from "./tabs/tab-perfil";
import { TabPublicacao } from "./tabs/tab-publicacao";
import { TabRecursos } from "./tabs/tab-recursos";
import { TabSegredosVariaveis } from "./tabs/tab-segredos-variaveis";
import { TabSkills } from "./tabs/tab-skills";

const STEP_KEYS = [
  "identidade",
  "comportamento",
  "recursos",
  "skills",
  "conhecimento",
  "integracoes",
  "segredos",
  "publicacao",
] as const;

const LEGACY_STEP_REDIRECTS: Record<string, (typeof STEP_KEYS)[number]> = {
  escopo: "integracoes",
};

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
      "Defina nome, aparência visual e conecte canais de comunicação como Telegram.",
    summary: "Quem é o agente e como ele se conecta.",
    icon: Fingerprint,
  },
  {
    key: "comportamento",
    label: "Comportamento",
    title: "Personalidade, instruções e limites",
    description:
      "Configure missão, instruções de operação, formato de resposta e guardrails de segurança em seções objetivas.",
    summary: "Personalidade, instruções, limites e autonomia.",
    icon: BrainCircuit,
  },
  {
    key: "recursos",
    label: "Recursos",
    title: "Modelo e voz",
    description:
      "Escolha o provider e modelo de raciocínio, defina orçamento e configure capacidades de voz.",
    summary: "Provider, modelo, orçamento e voz.",
    icon: Cpu,
  },
  {
    key: "skills",
    label: "Skills",
    title: "Skills especializadas",
    description:
      "Configure a política de skills, crie skills customizadas com controle individual de ativação.",
    summary: "Política de skills e skills customizadas.",
    icon: Wand2,
  },
  {
    key: "conhecimento",
    label: "Conhecimento",
    title: "Memória e grounding",
    description:
      "Configure memória persistente, RAG e revise candidatos de conhecimento e runbooks aprovados.",
    summary: "Memória, RAG e governança de conhecimento.",
    icon: Database,
  },
  {
    key: "integracoes",
    label: "Integrações",
    title: "Integrações do agente",
    description:
      "Conecte e controle quais integrações core e servidores MCP este agente pode acessar.",
    summary: "Integrações core e MCPs.",
    icon: Plug,
  },
  {
    key: "segredos",
    label: "Segredos & Variáveis",
    title: "Segredos e variáveis",
    description:
      "Conceda acesso a segredos globais e variáveis compartilhadas, e gerencie variáveis locais do agente.",
    summary: "Grants de secrets e env vars.",
    icon: KeyRound,
  },
  {
    key: "publicacao",
    label: "Publicação",
    title: "Salvar e publicar",
    description:
      "Revise as alterações pendentes e publique o agente com um único clique.",
    summary: "Resumo, salvar e publicar.",
    icon: Rocket,
  },
];

const STEP_COMPONENTS: Record<StepKey, ComponentType> = {
  identidade: TabPerfil,
  comportamento: TabInstrucoes,
  recursos: TabRecursos,
  skills: TabSkills,
  conhecimento: TabConhecimento,
  integracoes: TabIntegracoes,
  segredos: TabSegredosVariaveis,
  publicacao: TabPublicacao,
};

function dirtyForStep(step: StepKey, state: ReturnType<typeof useAgentEditor>["state"]) {
  if (step === "identidade") return state.dirty.meta;
  if (step === "comportamento") return state.dirty.agentSpec || state.dirty.documents;
  if (step === "recursos") return state.dirty.agentSpec || state.dirty.documents;
  if (step === "conhecimento") {
    return state.dirty.collections || state.dirty.agentSpec || state.dirty.documents;
  }
  if (step === "skills") return state.dirty.agentSpec;
  if (step === "integracoes") return state.dirty.agentSpec;
  if (step === "segredos") return state.dirty.agentSpec;
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
  const { state } = useAgentEditor();
  const { tl } = useAppI18n();

  const agentId = state.agent.id;

  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-2 lg:px-5 lg:py-2" {...tourAnchor("editor.header")}>
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/control-plane"
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-secondary)] hover:bg-[var(--surface-tint)]"
            aria-label={tl("Voltar ao catalogo")}
          >
            <ArrowLeft size={16} />
          </Link>
          <span className="inline-flex shrink-0 items-center justify-center">
            <AgentSigil
              agentId={agentId}
              label={state.displayName || agentId}
              color={state.color || "#8B8B93"}
              status={state.status}
              size="sm"
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
                {agentId}
              </span>
            </div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2.5">
              <h1 className="truncate text-[1.28rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {state.displayName || agentId}
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
                className={cn(
                  "inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm shadow-none transition-colors",
                  nextStep
                    ? "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-elevated)]"
                    : "font-semibold text-[var(--interactive-active-text)]",
                )}
                style={nextStep ? undefined : {
                  background: "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                  border: "1px solid var(--interactive-active-border)",
                }}
                {...tourAnchor("editor.next-step")}
              >
                {nextStep ? tl("Avançar") : tl("Salvar e Publicar")}
                {nextStep ? <ArrowRight size={15} /> : null}
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
}: {
  activeStep: StepKey;
}) {
  const ActiveComponent = STEP_COMPONENTS[activeStep];
  if (!ActiveComponent) return null;

  return (
    <div key={activeStep} {...tourAnchor(`editor.step.${activeStep}`)}>
      <ActiveComponent />
    </div>
  );
}

function InnerShell() {
  const { state, persistDraft, discardDraft } = useAgentEditor();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending, getStatus } = useAsyncAction();
  const { activeTab, setActiveTab } = useTabNavigation([...STEP_KEYS], {
    redirects: LEGACY_STEP_REDIRECTS,
  });

  const currentStepIndex = Math.max(
    0,
    STEP_KEYS.indexOf(activeTab as StepKey),
  );
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

  async function handleSaveAndPublish() {
    await runAction(
      "save-editor",
      async () => {
        await persistDraft({ includeAgentSpec: true });
        await requestJson(`/api/control-plane/agents/${state.agent.id}/publish`, {
          method: "POST",
        });
        router.refresh();
      },
      {
        successMessage: tl("Agente publicado com sucesso."),
        errorMessage: tl("Erro ao publicar."),
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
          onNext={nextStep ? () => handleStepChange(nextStep.key) : handleSaveAndPublish}
          onDiscard={discardDraft}
          onSave={handleSaveDraft}
          isSaving={isPending("save-editor")}
          saveStatus={getStatus("save-editor")}
        />

        <div className="grid h-full min-h-0 flex-1 overflow-hidden lg:grid-cols-[auto_minmax(0,1fr)]">
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
                        "group relative flex shrink-0 items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors duration-200",
                        isActive
                          ? "bg-[var(--surface-tint)]"
                          : "bg-transparent hover:bg-[var(--surface-tint)]",
                      )}
                    >
                      {/* Icon — no border, minimal */}
                      <span
                        className={cn(
                          "inline-flex h-7 w-7 shrink-0 items-center justify-center transition-colors",
                          isActive
                            ? "text-[var(--text-primary)]"
                            : isCompleted
                              ? "text-[var(--tone-success-dot)]"
                              : "text-[var(--text-quaternary)]",
                        )}
                      >
                        {step.completed ? <Check size={17} /> : <Icon size={17} />}
                      </span>

                      {/* Label */}
                      <span
                        className={cn(
                          "whitespace-nowrap text-sm font-medium",
                          isActive
                            ? "text-[var(--text-primary)]"
                            : isCompleted
                              ? "text-[var(--text-secondary)]"
                              : "text-[var(--text-tertiary)]",
                        )}
                      >
                        {tl(step.label)}
                      </span>

                      {step.dirty ? (
                        <span
                          className="inline-block h-1.5 w-1.5 shrink-0 rounded-full animate-pulse"
                          style={{ backgroundColor: "var(--tone-warning-dot)" }}
                          aria-label={tl("Alteracoes nao salvas")}
                        />
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </aside>

          <div className="relative flex h-full min-h-0 flex-col overflow-hidden" {...tourAnchor("editor.active-step")}>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 lg:px-8 lg:py-6">
              <ActiveStepRenderer activeStep={activeStep.key} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface AgentEditorShellProps {
  agent: ControlPlaneAgent;
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
  executionPolicyPayload?: ControlPlaneExecutionPolicyPayload | null;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
    integrations?: ControlPlaneCoreIntegrations;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
}

export function AgentEditorShell({
  agent,
  compiledPromptPayload,
  executionPolicyPayload,
  core,
  workspaces,
  systemSettings,
}: AgentEditorShellProps) {
  return (
    <AgentEditorProvider
      agent={agent}
      compiledPromptPayload={compiledPromptPayload}
      executionPolicyPayload={executionPolicyPayload}
      core={core}
      workspaces={workspaces}
      systemSettings={systemSettings}
    >
      <InnerShell />
    </AgentEditorProvider>
  );
}
