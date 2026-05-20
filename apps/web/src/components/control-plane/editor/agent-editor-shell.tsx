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
  Pause,
  Play,
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
import { getAgentLifecycleState } from "@/lib/agent-lifecycle";
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
    label: "controlPlane.agentEditor.steps.identidade.label",
    title: "controlPlane.agentEditor.steps.identidade.title",
    description: "controlPlane.agentEditor.steps.identidade.description",
    summary: "controlPlane.agentEditor.steps.identidade.summary",
    icon: Fingerprint,
  },
  {
    key: "comportamento",
    label: "controlPlane.agentEditor.steps.comportamento.label",
    title: "controlPlane.agentEditor.steps.comportamento.title",
    description: "controlPlane.agentEditor.steps.comportamento.description",
    summary: "controlPlane.agentEditor.steps.comportamento.summary",
    icon: BrainCircuit,
  },
  {
    key: "recursos",
    label: "controlPlane.agentEditor.steps.recursos.label",
    title: "controlPlane.agentEditor.steps.recursos.title",
    description: "controlPlane.agentEditor.steps.recursos.description",
    summary: "controlPlane.agentEditor.steps.recursos.summary",
    icon: Cpu,
  },
  {
    key: "skills",
    label: "controlPlane.agentEditor.steps.skills.label",
    title: "controlPlane.agentEditor.steps.skills.title",
    description: "controlPlane.agentEditor.steps.skills.description",
    summary: "controlPlane.agentEditor.steps.skills.summary",
    icon: Wand2,
  },
  {
    key: "conhecimento",
    label: "controlPlane.agentEditor.steps.conhecimento.label",
    title: "controlPlane.agentEditor.steps.conhecimento.title",
    description: "controlPlane.agentEditor.steps.conhecimento.description",
    summary: "controlPlane.agentEditor.steps.conhecimento.summary",
    icon: Database,
  },
  {
    key: "integracoes",
    label: "controlPlane.agentEditor.steps.integracoes.label",
    title: "controlPlane.agentEditor.steps.integracoes.title",
    description: "controlPlane.agentEditor.steps.integracoes.description",
    summary: "controlPlane.agentEditor.steps.integracoes.summary",
    icon: Plug,
  },
  {
    key: "segredos",
    label: "controlPlane.agentEditor.steps.segredos.label",
    title: "controlPlane.agentEditor.steps.segredos.title",
    description: "controlPlane.agentEditor.steps.segredos.description",
    summary: "controlPlane.agentEditor.steps.segredos.summary",
    icon: KeyRound,
  },
  {
    key: "publicacao",
    label: "controlPlane.agentEditor.steps.publicacao.label",
    title: "controlPlane.agentEditor.steps.publicacao.title",
    description: "controlPlane.agentEditor.steps.publicacao.description",
    summary: "controlPlane.agentEditor.steps.publicacao.summary",
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
  onLifecycleToggle,
  isLifecyclePending,
  lifecycleStatus,
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
  onLifecycleToggle: () => Promise<void>;
  isLifecyclePending: boolean;
  lifecycleStatus: "idle" | "pending" | "success" | "error";
}) {
  const { state } = useAgentEditor();
  const { t } = useAppI18n();

  const agentId = state.agent.id;
  const lifecycle = getAgentLifecycleState({
    status: state.agent.status,
    appliedVersion: state.agent.applied_version ?? null,
    desiredVersion: state.agent.desired_version ?? null,
    hasPendingChanges: hasUnsavedChanges,
  });
  const lifecycleDescription = t(lifecycle.descriptionKey, lifecycle.descriptionOptions);

  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-2 lg:px-5 lg:py-2" {...tourAnchor("editor.header")}>
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/control-plane"
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-secondary)] hover:bg-[var(--surface-tint)]"
            aria-label={t("generated.controlPlane.voltar_ao_catalogo_9b2761dd")}
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
                {t("generated.controlPlane.agentes_8ecacbc4")}
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
                {t("generated.controlPlane.voltar_b8c5183d")}
              </button>
              <button
                type="button"
                onClick={onNext}
                className={cn(
                  "inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm shadow-none transition-colors",
                  nextStep
                    ? "border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-elevated)]"
                    : "font-semibold text-[color:var(--interactive-active-text)]",
                )}
                style={nextStep ? undefined : {
                  background: "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                  border: "1px solid var(--interactive-active-border)",
                  color: "var(--interactive-active-text)",
                }}
                {...tourAnchor("editor.next-step")}
              >
                {nextStep ? t("generated.controlPlane.avancar_ebff1b86") : t("generated.controlPlane.salvar_e_publicar_70d8a389")}
                {nextStep ? <ArrowRight size={15} /> : null}
              </button>
              {lifecycle.toggle !== "none" ? (
                <>
                  <span className="mx-1 hidden h-5 w-px bg-[var(--border-subtle)] lg:block" />
                  <AsyncActionButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    icon={lifecycle.toggle === "activate" ? Play : Pause}
                    onClick={onLifecycleToggle}
                    loading={isLifecyclePending}
                    loadingLabel={
                      lifecycle.toggle === "activate" ? t("generated.controlPlane.ativando_d8dad0b2") : t("generated.controlPlane.pausando_eef1e878")
                    }
                    status={lifecycleStatus}
                    className="shadow-none"
                    title={lifecycleDescription}
                    {...tourAnchor("editor.lifecycle")}
                  >
                    {lifecycle.toggle === "activate" ? t("generated.controlPlane.ativar_db54d834") : t("generated.controlPlane.pausar_85f3ee9b")}
                  </AsyncActionButton>
                </>
              ) : null}
              {hasUnsavedChanges ? (
                <>
                  <span className="mx-1 hidden h-5 w-px bg-[var(--border-subtle)] lg:block" />
                  <button
                    type="button"
                    onClick={onDiscard}
                    className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-transparent px-3.5 py-2 text-sm text-[var(--text-secondary)] shadow-none transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                    {...tourAnchor("editor.discard")}
                  >
                    {t("generated.controlPlane.descartar_8c52be0d")}
                  </button>
                  <AsyncActionButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={onSave}
                    loading={isSaving}
                    loadingLabel={t("generated.controlPlane.salvando_7eeded02")}
                    status={saveStatus}
                    className="shadow-none"
                    {...tourAnchor("editor.save")}
                  >
                    {t("generated.controlPlane.salvar_94c457df")}
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
  const { state, persistDraft, discardDraft, applyAgentLifecycle } = useAgentEditor();
  const { t, tl } = useAppI18n();
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
        successMessage: t("generated.controlPlane.alteracoes_salvas_com_sucesso_bd2115c7"),
        errorMessage: t("generated.controlPlane.erro_ao_salvar_alteracoes_c46bb65c"),
      },
    );
  }

  async function handleLifecycleToggle() {
    const lifecycle = getAgentLifecycleState({
      status: state.agent.status,
      appliedVersion: state.agent.applied_version ?? null,
      desiredVersion: state.agent.desired_version ?? null,
      hasPendingChanges: hasUnsavedChanges,
    });
    const action = lifecycle.toggle;
    if (action === "none") return;
    // Optimistic update — flip the runtime status the moment the user clicks
    // so the badge/icon never lags behind the click. The API response below
    // will overwrite this with the canonical server state, and router.refresh
    // re-hydrates secondary data (workers list, version history, etc.).
    applyAgentLifecycle({ status: action === "activate" ? "active" : "paused" });
    await runAction(
      "lifecycle-toggle",
      async () => {
        const response = await requestJson<{
          status?: string;
          applied_version?: number | null;
          desired_version?: number | null;
        }>(`/api/control-plane/agents/${state.agent.id}/${action}`, {
          method: "POST",
        });
        applyAgentLifecycle({
          status: response.status ?? null,
          appliedVersion: response.applied_version ?? null,
          desiredVersion: response.desired_version ?? null,
        });
        router.refresh();
      },
      {
        successMessage:
          action === "activate" ? t("generated.controlPlane.agente_ativado_8208fe03") : t("generated.controlPlane.agente_pausado_1bd6570f"),
        errorMessage:
          action === "activate"
            ? t("generated.controlPlane.erro_ao_ativar_agente_dafb0faf")
            : t("generated.controlPlane.erro_ao_pausar_agente_e64a0fa1"),
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
        successMessage: t("generated.controlPlane.agente_publicado_com_sucesso_faf7b7d4"),
        errorMessage: t("generated.controlPlane.erro_ao_publicar_a6c27ea7"),
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
          onLifecycleToggle={handleLifecycleToggle}
          isLifecyclePending={isPending("lifecycle-toggle")}
          lifecycleStatus={getStatus("lifecycle-toggle")}
        />

        <div className="grid h-full min-h-0 flex-1 overflow-hidden lg:grid-cols-[auto_minmax(0,1fr)]">
          <aside className="h-full min-h-0 border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] lg:border-b-0 lg:border-r" {...tourAnchor("editor.step-rail")}>
            <div className="flex h-full flex-col px-2 py-3 lg:px-2.5 lg:py-4">
              <div className="mb-2 px-1.5">
                <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--text-quaternary)]">
                  {t("generated.controlPlane.fluxo_16a7913a")}
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
                          aria-label={t("generated.controlPlane.alteracoes_nao_salvas_c5136366")}
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
