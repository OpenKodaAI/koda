"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, ShieldAlert, Wand2 } from "lucide-react";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { COLLAPSE_TRANSITION } from "@/components/control-plane/shared/motion-constants";
import { FormInput, FormSelect } from "@/components/control-plane/shared/form-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { ListEditorField } from "@/components/control-plane/shared/list-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { SoftTabs, type SoftTabItem } from "@/components/ui/soft-tabs";
import {
  parseAutonomyPolicy,
  parseHardRules,
  parseInteractionStyle,
  parseMissionProfile,
  parseOperatingInstructions,
  parseResponsePolicy,
  serializeAutonomyPolicy,
  serializeHardRules,
  serializeInteractionStyle,
  serializeMissionProfile,
  serializeOperatingInstructions,
  serializeResponsePolicy,
} from "@/lib/policy-serializers";

type InnerTab = "prompts" | "politicas";

const PROMPT_BLOCKS: Array<{
  id: "identity_md" | "soul_md" | "system_prompt_md" | "instructions_md" | "rules_md";
  label: string;
  description: string;
  minHeight: string;
}> = [
  {
    id: "instructions_md",
    label: "Instruções",
    description: "Como o agente deve processar solicitações, quando escalar, critérios de sucesso.",
    minHeight: "280px",
  },
  {
    id: "system_prompt_md",
    label: "System Prompt",
    description: "Diretriz central passada ao LLM antes de qualquer mensagem.",
    minHeight: "260px",
  },
  {
    id: "rules_md",
    label: "Regras",
    description: "Regras invioláveis, guardrails de segurança e limites.",
    minHeight: "220px",
  },
  {
    id: "identity_md",
    label: "Identidade",
    description: "Nome, papel profissional e contexto básico do agente.",
    minHeight: "220px",
  },
  {
    id: "soul_md",
    label: "Soul",
    description: "Personalidade, tom e valores do agente em prosa livre.",
    minHeight: "220px",
  },
];

export function TabInstrucoes() {
  const {
    state,
    developerMode,
    updateDocument,
    updateAgentSpecField,
  } = useAgentEditor();
  const { tl } = useAppI18n();

  const [innerTab, setInnerTab] = useState<InnerTab>("prompts");
  const [activePromptBlock, setActivePromptBlock] = useState<
    (typeof PROMPT_BLOCKS)[number]["id"]
  >("instructions_md");

  const missionProfile = useMemo(
    () => parseMissionProfile(state.missionProfileJson),
    [state.missionProfileJson],
  );
  const interactionStyle = useMemo(
    () => parseInteractionStyle(state.interactionStyleJson),
    [state.interactionStyleJson],
  );
  const operatingInstructions = useMemo(
    () => parseOperatingInstructions(state.operatingInstructionsJson),
    [state.operatingInstructionsJson],
  );
  const hardRules = useMemo(
    () => parseHardRules(state.hardRulesJson),
    [state.hardRulesJson],
  );
  const responsePolicy = useMemo(
    () => parseResponsePolicy(state.responsePolicyJson),
    [state.responsePolicyJson],
  );
  const autonomyPolicy = useMemo(
    () => parseAutonomyPolicy(state.autonomyPolicyJson),
    [state.autonomyPolicyJson],
  );

  function updateMissionProfile(patch: Partial<typeof missionProfile>) {
    updateAgentSpecField(
      "missionProfileJson",
      serializeMissionProfile({ ...missionProfile, ...patch }),
    );
  }

  function updateInteractionStyle(patch: Partial<typeof interactionStyle>) {
    updateAgentSpecField(
      "interactionStyleJson",
      serializeInteractionStyle({ ...interactionStyle, ...patch }),
    );
  }

  function updateOperatingInstructions(
    patch: Partial<typeof operatingInstructions>,
  ) {
    updateAgentSpecField(
      "operatingInstructionsJson",
      serializeOperatingInstructions({ ...operatingInstructions, ...patch }),
    );
  }

  function updateHardRules(patch: Partial<typeof hardRules>) {
    updateAgentSpecField(
      "hardRulesJson",
      serializeHardRules({ ...hardRules, ...patch }),
    );
  }

  function updateResponsePolicy(patch: Partial<typeof responsePolicy>) {
    updateAgentSpecField(
      "responsePolicyJson",
      serializeResponsePolicy({ ...responsePolicy, ...patch }),
    );
  }

  function updateAutonomyPolicy(patch: Partial<typeof autonomyPolicy>) {
    updateAgentSpecField(
      "autonomyPolicyJson",
      serializeAutonomyPolicy({ ...autonomyPolicy, ...patch }),
    );
  }

  const innerTabs: SoftTabItem[] = [
    { id: "prompts", label: tl("Prompts"), icon: <Wand2 size={13} /> },
    { id: "politicas", label: tl("Politicas"), icon: <ShieldAlert size={13} /> },
  ];

  const activeBlock =
    PROMPT_BLOCKS.find((block) => block.id === activePromptBlock) ?? PROMPT_BLOCKS[0];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SoftTabs
          items={innerTabs}
          value={innerTab}
          onChange={(id) => setInnerTab(id as InnerTab)}
          ariaLabel={tl("Secoes de instrucoes")}
        />
        <span className="text-xs text-[var(--text-quaternary)]">
          {innerTab === "prompts"
            ? tl("Blocos markdown enviados ao modelo")
            : tl("Limites, autonomia e execucao")}
        </span>
      </div>

      {innerTab === "prompts" && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <SoftTabs
              items={PROMPT_BLOCKS.map((block) => ({
                id: block.id,
                label: tl(block.label),
              }))}
              value={activePromptBlock}
              onChange={(id) =>
                setActivePromptBlock(id as (typeof PROMPT_BLOCKS)[number]["id"])
              }
              ariaLabel={tl("Bloco de prompt ativo")}
            />
            <span className="text-xs text-[var(--text-quaternary)]">
              {tl(activeBlock.description)}
            </span>
          </div>
          <MarkdownEditorField
            hideFieldHeader
            textareaAriaLabel={tl(activeBlock.label)}
            value={state.documents[activeBlock.id] ?? ""}
            onChange={(value) => updateDocument(activeBlock.id, value)}
            minHeight={activeBlock.minHeight}
            placeholder={tl(activeBlock.description)}
          />
        </section>
      )}

      {innerTab === "politicas" && (
        <>
          <PolicyCard title={tl("Formato de resposta")} icon={FileText} variant="flat" defaultOpen>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <FormSelect
                label={tl("Idioma")}
                value={responsePolicy.language}
                onChange={(event) =>
                  updateResponsePolicy({ language: event.target.value })
                }
                options={[
                  { value: "pt-BR", label: tl("Portugues (Brasil)") },
                  { value: "en-US", label: "English (US)" },
                  { value: "es-ES", label: "Español" },
                ]}
              />
              <FormSelect
                label={tl("Formato")}
                value={responsePolicy.format}
                onChange={(event) =>
                  updateResponsePolicy({ format: event.target.value })
                }
                options={[
                  { value: "markdown", label: "Markdown" },
                  { value: "plain_text", label: tl("Texto simples") },
                  { value: "structured", label: tl("Estruturado") },
                ]}
              />
              <FormSelect
                label={tl("Concisao")}
                value={responsePolicy.conciseness}
                onChange={(event) =>
                  updateResponsePolicy({ conciseness: event.target.value })
                }
                options={[
                  { value: "succinct", label: tl("Enxuto") },
                  { value: "balanced", label: tl("Equilibrado") },
                  { value: "detailed", label: tl("Detalhado") },
                ]}
              />
            </div>
            <FormInput
              label={tl("Quality bar")}
              value={responsePolicy.quality_bar}
              onChange={(event) =>
                updateResponsePolicy({ quality_bar: event.target.value })
              }
              placeholder={tl("Ex: profissional, rastreavel, sem invencao")}
            />
          </PolicyCard>

          <PolicyCard
            title={tl("Autonomia e aprovacao")}
            description={tl("Guardrails aplicados pelo runtime antes de executar tools — nao e texto no prompt.")}
            icon={ShieldAlert}
            variant="flat"
            defaultOpen
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormSelect
                label={tl("Modo de aprovacao")}
                value={autonomyPolicy.default_approval_mode}
                onChange={(event) =>
                  updateAutonomyPolicy({
                    default_approval_mode: event.target.value,
                  })
                }
                options={[
                  { value: "read_only", label: tl("Somente leitura"), description: tl("Agente nao executa acoes de escrita") },
                  { value: "guarded", label: tl("Protegido"), description: tl("Acoes de escrita requerem confirmacao") },
                  { value: "supervised", label: tl("Supervisionado"), description: tl("Agente pede aprovacao antes de executar") },
                  { value: "escalation_required", label: tl("Escalacao obrigatoria"), description: tl("Todas as acoes devem ser escaladas") },
                ]}
              />
              <FormSelect
                label={tl("Nivel de autonomia")}
                value={autonomyPolicy.default_autonomy_tier}
                onChange={(event) =>
                  updateAutonomyPolicy({
                    default_autonomy_tier: event.target.value,
                  })
                }
                options={[
                  { value: "t0", label: "T0 — " + tl("Minima"), description: tl("Sem acoes autonomas") },
                  { value: "t1", label: "T1 — " + tl("Moderada"), description: tl("Acoes de leitura livres") },
                  { value: "t2", label: "T2 — " + tl("Ampla"), description: tl("Execucao autonoma com guardrails") },
                ]}
              />
            </div>
          </PolicyCard>
        </>
      )}

      <AnimatePresence>
        {developerMode && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={COLLAPSE_TRANSITION}
            className="overflow-hidden"
          >
            <div className="glass-card p-6 flex flex-col gap-6">
              <SectionCollapsible title={tl("Campos avancados")}>
                <div className="flex flex-col gap-6 pt-2">
                  <ListEditorField
                    label={tl("Outcomes principais")}
                    items={missionProfile.primary_outcomes}
                    onChange={(items) =>
                      updateMissionProfile({ primary_outcomes: items })
                    }
                    placeholder={tl("Ex: reduzir tempo de triagem")}
                  />
                  <ListEditorField
                    label={tl("Success metrics")}
                    description={tl("Indicadores usados para medir se o agente esta gerando valor com qualidade.")}
                    items={missionProfile.kpis}
                    onChange={(items) => updateMissionProfile({ kpis: items })}
                    placeholder={tl("Ex: acuracia, lead time, cobertura de fontes")}
                  />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormInput
                      label={tl("Politica de citacao")}
                      value={responsePolicy.citation_policy}
                      onChange={(event) =>
                        updateResponsePolicy({ citation_policy: event.target.value })
                      }
                      placeholder={tl("Ex: citar label e data quando grounded")}
                    />
                    <FormInput
                      label={tl("Politica de fontes")}
                      value={responsePolicy.source_policy}
                      onChange={(event) =>
                        updateResponsePolicy({ source_policy: event.target.value })
                      }
                      placeholder={tl("Ex: preferir knowledge canonico e runbooks")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={tl("Workflow padrao")}
                      items={operatingInstructions.default_workflow}
                      onChange={(items) =>
                        updateOperatingInstructions({ default_workflow: items })
                      }
                      placeholder={tl("Ex: entender, buscar grounding, agir, verificar")}
                    />
                    <ListEditorField
                      label={tl("Heuristicas de execucao")}
                      items={operatingInstructions.execution_heuristics}
                      onChange={(items) =>
                        updateOperatingInstructions({ execution_heuristics: items })
                      }
                      placeholder={tl("Ex: usar modelo menor para triagem")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={tl("Criterios de sucesso")}
                      items={operatingInstructions.success_criteria}
                      onChange={(items) =>
                        updateOperatingInstructions({ success_criteria: items })
                      }
                      placeholder={tl("Ex: resposta correta, segura e verificavel")}
                    />
                    <ListEditorField
                      label={tl("Expectativas de handoff")}
                      items={operatingInstructions.handoff_expectations}
                      onChange={(items) =>
                        updateOperatingInstructions({ handoff_expectations: items })
                      }
                      placeholder={tl("Ex: escalar com contexto e proxima acao sugerida")}
                    />
                  </div>
                  <ListEditorField
                    label={tl("Requisitos de aprovacao")}
                    items={hardRules.approval_requirements}
                    onChange={(items) =>
                      updateHardRules({ approval_requirements: items })
                    }
                    placeholder={tl("Ex: producao exige confirmacao humana")}
                  />
                  <ListEditorField
                    label={tl("Regras inviolaveis (legado)")}
                    description={tl("Conteudo redundante com rules_md — prefira o bloco de prompt.")}
                    items={hardRules.non_negotiables}
                    onChange={(items) =>
                      updateHardRules({ non_negotiables: items })
                    }
                    placeholder={tl("Ex: nao inventar fatos")}
                  />
                  <ListEditorField
                    label={tl("Acoes proibidas (legado)")}
                    description={tl("Conteudo redundante com rules_md — prefira o bloco de prompt.")}
                    items={hardRules.forbidden_actions}
                    onChange={(items) =>
                      updateHardRules({ forbidden_actions: items })
                    }
                    placeholder={tl("Ex: deploy sem aprovacao explicita")}
                  />
                  <ListEditorField
                    label={tl("Regras de seguranca (legado)")}
                    description={tl("Conteudo redundante com rules_md — prefira o bloco de prompt.")}
                    items={hardRules.security_rules}
                    onChange={(items) =>
                      updateHardRules({ security_rules: items })
                    }
                    placeholder={tl("Ex: nao expor segredos ou PII")}
                  />
                </div>
              </SectionCollapsible>

              <SectionCollapsible title={tl("Overrides avancados de prompt e autonomia")}>
                <div className="flex flex-col gap-6 pt-2">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormInput
                      label={tl("Funcao profissional")}
                      description={tl("Campo legado. Prefira descrever o papel em identity_md ou soul_md.")}
                      value={missionProfile.role}
                      onChange={(event) =>
                        updateMissionProfile({ role: event.target.value })
                      }
                      placeholder={tl("Ex: SRE autonomo supervisionado")}
                    />
                    <FormInput
                      label={tl("Persona")}
                      value={interactionStyle.persona}
                      onChange={(event) =>
                        updateInteractionStyle({ persona: event.target.value })
                      }
                      placeholder={tl("Ex: funcionario tecnico confiavel")}
                    />
                  </div>
                  <MarkdownEditorField
                    label={tl("Audiencia e contexto (legado)")}
                    value={missionProfile.audience}
                    onChange={(value) => updateMissionProfile({ audience: value })}
                    minHeight="160px"
                    placeholder={tl("Descreva o publico, o tipo de tarefa, restricoes operacionais, canais atendidos e qualquer contexto importante em Markdown.")}
                  />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <FormSelect
                      label={tl("Tom")}
                      value={interactionStyle.tone}
                      onChange={(event) =>
                        updateInteractionStyle({ tone: event.target.value })
                      }
                      options={[
                        { value: "profissional", label: tl("Profissional") },
                        { value: "calmo", label: tl("Calmo") },
                        { value: "direto", label: tl("Direto") },
                        { value: "colaborativo", label: tl("Colaborativo") },
                      ]}
                    />
                    <FormSelect
                      label={tl("Modo de colaboracao")}
                      value={interactionStyle.collaboration_style}
                      onChange={(event) =>
                        updateInteractionStyle({
                          collaboration_style: event.target.value,
                        })
                      }
                      options={[
                        { value: "colaborativo", label: tl("Colaborativo") },
                        { value: "executor", label: tl("Executor") },
                        { value: "consultivo", label: tl("Consultivo") },
                        { value: "investigativo", label: tl("Investigativo") },
                      ]}
                    />
                    <FormInput
                      label={tl("Estilo de escalacao")}
                      value={interactionStyle.escalation_style}
                      onChange={(event) =>
                        updateInteractionStyle({ escalation_style: event.target.value })
                      }
                      placeholder={tl("Ex: escalar com contexto e proposta")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={tl("Valores")}
                      items={interactionStyle.values}
                      onChange={(items) => updateInteractionStyle({ values: items })}
                      placeholder={tl("Ex: honestidade, grounding, ownership")}
                    />
                    <div className="flex flex-col gap-4">
                      <FormInput
                        label={tl("Estilo de escrita")}
                        value={interactionStyle.writing_style}
                        onChange={(event) =>
                          updateInteractionStyle({ writing_style: event.target.value })
                        }
                        placeholder={tl("Ex: conciso, objetivo e rastreavel")}
                      />
                      <ListEditorField
                        label={tl("Responsibility limits (legacy)")}
                        items={missionProfile.responsibility_limits}
                        onChange={(items) =>
                          updateMissionProfile({ responsibility_limits: items })
                        }
                        placeholder={tl("Ex: nao aprovar deploy em producao")}
                      />
                    </div>
                  </div>
                  <JsonEditorField
                    label={tl("Autonomy Policy JSON")}
                    description={tl("Schema canonico completo de autonomia, incluindo task_overrides.")}
                    value={state.autonomyPolicyJson}
                    onChange={(value) =>
                      updateAgentSpecField("autonomyPolicyJson", value)
                    }
                  />
                  <JsonEditorField
                    label={tl("Execution Policy JSON")}
                    description={tl("Politica central de execucao e fator humano. Use este campo para regras por tool, integration e action.")}
                    value={state.executionPolicyJson}
                    onChange={(value) =>
                      updateAgentSpecField("executionPolicyJson", value)
                    }
                  />
                </div>
              </SectionCollapsible>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
