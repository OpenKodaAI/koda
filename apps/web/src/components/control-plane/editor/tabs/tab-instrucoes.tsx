"use client";

import { useMemo } from "react";
import { Shield, Sparkles } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FormInput, FormSelect } from "@/components/control-plane/shared/form-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { ListEditorField } from "@/components/control-plane/shared/list-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
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

export function TabInstrucoes() {
  const {
    state,
    developerMode,
    updateDocument,
    updateAgentSpecField,
  } = useBotEditor();
  const { tl } = useAppI18n();

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

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={tl("Missao e governanca")}
          description={tl("Objetivo, publico, forma de resposta e limites operacionais reais do agente.")}
          icon={Sparkles}
          dirty={state.dirty.agentSpec}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormInput
              label={tl("Missao")}
              description={tl("O objetivo central do agente.")}
              value={missionProfile.mission}
              onChange={(event) =>
                updateMissionProfile({ mission: event.target.value })
              }
              placeholder={tl("Ex: Resolver tickets e incidentes com grounding")}
            />
            <FormInput
              label={tl("Papel")}
              description={tl("Funcao profissional desempenhada pelo agente.")}
              value={missionProfile.role}
              onChange={(event) =>
                updateMissionProfile({ role: event.target.value })
              }
              placeholder={tl("Ex: SRE autonomo supervisionado")}
            />
          </div>

          <MarkdownEditorField
            label={tl("Publico e contexto")}
            description={tl("Quem recebe as respostas e em que contexto ele atua.")}
            value={missionProfile.audience}
            onChange={(value) => updateMissionProfile({ audience: value })}
            minHeight="260px"
            placeholder={tl("Descreva o publico, o tipo de tarefa, restricoes operacionais, canais atendidos e qualquer contexto importante em Markdown.")}
          />

          <ListEditorField
            label={tl("Outcomes principais")}
            description={tl("Resultados que o agente deve perseguir continuamente.")}
            items={missionProfile.primary_outcomes}
            onChange={(items) =>
              updateMissionProfile({ primary_outcomes: items })
            }
            placeholder={tl("Ex: reduzir tempo de triagem")}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ListEditorField
              label={tl("Success metrics")}
              description={tl("Indicadores usados para medir se o agente esta gerando valor com qualidade.")}
              items={missionProfile.kpis}
              onChange={(items) => updateMissionProfile({ kpis: items })}
              placeholder={tl("Ex: acuracia, lead time, cobertura de fontes")}
            />
            <div className="rounded-lg border border-[var(--border-subtle)] p-4 text-sm text-[var(--text-tertiary)]">
              {tl("Os limites operacionais do fluxo principal agora ficam concentrados em hard rules e autonomy policy para evitar configuracoes duplicadas e conflitantes.")}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
          </div>
        </PolicyCard>
      </section>

      <section className="flex flex-col gap-6 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Resposta, operacao e guardrails")}
          description={tl("Como o agente responde, decide e se contém.")}
          icon={Shield}
        >
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

          <FormInput
            label={tl("Quality bar")}
            value={responsePolicy.quality_bar}
            onChange={(event) =>
              updateResponsePolicy({ quality_bar: event.target.value })
            }
            placeholder={tl("Ex: profissional, rastreavel, sem invencao")}
          />

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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ListEditorField
              label={tl("Nao negociaveis")}
              items={hardRules.non_negotiables}
              onChange={(items) =>
                updateHardRules({ non_negotiables: items })
              }
              placeholder={tl("Ex: nao inventar fatos")}
            />
            <ListEditorField
              label={tl("Acoes proibidas")}
              items={hardRules.forbidden_actions}
              onChange={(items) =>
                updateHardRules({ forbidden_actions: items })
              }
              placeholder={tl("Ex: deploy sem aprovacao explicita")}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ListEditorField
              label={tl("Requisitos de aprovacao")}
              items={hardRules.approval_requirements}
              onChange={(items) =>
                updateHardRules({ approval_requirements: items })
              }
              placeholder={tl("Ex: producao exige confirmacao humana")}
            />
            <ListEditorField
              label={tl("Regras de seguranca")}
              items={hardRules.security_rules}
              onChange={(items) =>
                updateHardRules({ security_rules: items })
              }
              placeholder={tl("Ex: nao expor segredos ou PII")}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormSelect
              label={tl("Approval mode padrao")}
              value={autonomyPolicy.default_approval_mode}
              onChange={(event) =>
                updateAutonomyPolicy({
                  default_approval_mode: event.target.value,
                })
              }
              options={[
                { value: "read_only", label: tl("Read only") },
                { value: "guarded", label: tl("Guarded") },
                { value: "supervised", label: tl("Supervised") },
                {
                  value: "escalation_required",
                  label: tl("Escalation required"),
                },
              ]}
            />
            <FormSelect
              label={tl("Autonomy tier padrao")}
              value={autonomyPolicy.default_autonomy_tier}
              onChange={(event) =>
                updateAutonomyPolicy({
                  default_autonomy_tier: event.target.value,
                })
              }
              options={[
                { value: "t0", label: "T0" },
                { value: "t1", label: "T1" },
                { value: "t2", label: "T2" },
              ]}
            />
          </div>
        </PolicyCard>
      </section>

      {developerMode ? (
        <div className="glass-card p-6 flex flex-col gap-6">
          <SectionCollapsible title={tl("Prompts derivados e overrides avancados")}>
            <div className="flex flex-col gap-6 pt-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormInput
                  label={tl("Persona")}
                  value={interactionStyle.persona}
                  onChange={(event) =>
                    updateInteractionStyle({ persona: event.target.value })
                  }
                  placeholder={tl("Ex: funcionario tecnico confiavel")}
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
              <MarkdownEditorField
                label={tl("Identity")}
                value={state.documents.identity_md ?? ""}
                onChange={(value) => updateDocument("identity_md", value)}
                minHeight="180px"
              />
              <MarkdownEditorField
                label={tl("Soul / Interaction Style")}
                value={state.documents.soul_md ?? ""}
                onChange={(value) => updateDocument("soul_md", value)}
                minHeight="180px"
              />
              <MarkdownEditorField
                label={tl("System Prompt")}
                value={state.documents.system_prompt_md ?? ""}
                onChange={(value) => updateDocument("system_prompt_md", value)}
                minHeight="220px"
              />
              <MarkdownEditorField
                label={tl("Instructions")}
                value={state.documents.instructions_md ?? ""}
                onChange={(value) => updateDocument("instructions_md", value)}
                minHeight="220px"
              />
              <MarkdownEditorField
                label={tl("Rules")}
                value={state.documents.rules_md ?? ""}
                onChange={(value) => updateDocument("rules_md", value)}
                minHeight="180px"
              />
              <JsonEditorField
                label={tl("Autonomy Policy JSON")}
                description={tl("Schema canonico completo de autonomia, incluindo task_overrides.")}
                value={state.autonomyPolicyJson}
                onChange={(value) =>
                  updateAgentSpecField("autonomyPolicyJson", value)
                }
              />
            </div>
          </SectionCollapsible>
        </div>
      ) : null}

    </div>
  );
}
