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
    label: "controlPlane.instructionBlocks.instructions.label",
    description: "controlPlane.instructionBlocks.instructions.description",
    minHeight: "280px",
  },
  {
    id: "system_prompt_md",
    label: "controlPlane.instructionBlocks.systemPrompt.label",
    description: "controlPlane.instructionBlocks.systemPrompt.description",
    minHeight: "260px",
  },
  {
    id: "rules_md",
    label: "controlPlane.instructionBlocks.rules.label",
    description: "controlPlane.instructionBlocks.rules.description",
    minHeight: "220px",
  },
  {
    id: "identity_md",
    label: "controlPlane.instructionBlocks.identity.label",
    description: "controlPlane.instructionBlocks.identity.description",
    minHeight: "220px",
  },
  {
    id: "soul_md",
    label: "controlPlane.instructionBlocks.soul.label",
    description: "controlPlane.instructionBlocks.soul.description",
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
  const { t, tl } = useAppI18n();

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
    { id: "prompts", label: t("generated.controlPlane.prompts_ba404b40"), icon: <Wand2 size={13} /> },
    { id: "politicas", label: t("generated.controlPlane.politicas_138a663e"), icon: <ShieldAlert size={13} /> },
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
          ariaLabel={t("generated.controlPlane.secoes_de_instrucoes_4bcc394c")}
        />
        <span className="text-xs text-[var(--text-quaternary)]">
          {innerTab === "prompts"
            ? t("generated.controlPlane.blocos_markdown_enviados_ao_modelo_f0be0ee7")
            : t("generated.controlPlane.limites_autonomia_e_execucao_67dbe4f9")}
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
              ariaLabel={t("generated.controlPlane.bloco_de_prompt_ativo_fcbaa58e")}
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
          <PolicyCard title={t("generated.controlPlane.formato_de_resposta_15a4d767")} icon={FileText} variant="flat" defaultOpen>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <FormSelect
                label={t("generated.controlPlane.idioma_1bc8a0e5")}
                value={responsePolicy.language}
                onChange={(event) =>
                  updateResponsePolicy({ language: event.target.value })
                }
                options={[
                  { value: "pt-BR", label: t("generated.controlPlane.portugues_brasil_c608f345") },
                  { value: "en-US", label: t("generated.controlPlane.english_us_773cba0f") },
                  { value: "es-ES", label: t("generated.controlPlane.espanhol_d8623f06") },
                ]}
              />
              <FormSelect
                label={t("generated.controlPlane.formato_b4b0117b")}
                value={responsePolicy.format}
                onChange={(event) =>
                  updateResponsePolicy({ format: event.target.value })
                }
                options={[
                  { value: "markdown", label: t("generated.controlPlane.markdown_718e1b2b") },
                  { value: "plain_text", label: t("generated.controlPlane.texto_simples_fb771131") },
                  { value: "structured", label: t("generated.controlPlane.estruturado_c2995d50") },
                ]}
              />
              <FormSelect
                label={t("generated.controlPlane.concisao_292cdd70")}
                value={responsePolicy.conciseness}
                onChange={(event) =>
                  updateResponsePolicy({ conciseness: event.target.value })
                }
                options={[
                  { value: "succinct", label: t("generated.controlPlane.enxuto_84f7e566") },
                  { value: "balanced", label: t("generated.controlPlane.equilibrado_355b4eda") },
                  { value: "detailed", label: t("generated.controlPlane.detalhado_a58ae353") },
                ]}
              />
            </div>
            <FormInput
              label={t("generated.controlPlane.quality_bar_545f87d9")}
              value={responsePolicy.quality_bar}
              onChange={(event) =>
                updateResponsePolicy({ quality_bar: event.target.value })
              }
              placeholder={t("generated.controlPlane.ex_profissional_rastreavel_sem_invencao_2cada97e")}
            />
          </PolicyCard>

          <PolicyCard
            title={t("generated.controlPlane.autonomia_e_aprovacao_0afae868")}
            description={t("generated.controlPlane.guardrails_aplicados_pelo_runtime_antes_de_e_d0ef1019")}
            icon={ShieldAlert}
            variant="flat"
            defaultOpen
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormSelect
                label={t("generated.controlPlane.modo_de_aprovacao_108bd735")}
                value={autonomyPolicy.default_approval_mode}
                onChange={(event) =>
                  updateAutonomyPolicy({
                    default_approval_mode: event.target.value,
                  })
                }
                options={[
                  { value: "read_only", label: t("generated.controlPlane.somente_leitura_0f78d76a"), description: t("generated.controlPlane.agente_nao_executa_acoes_de_escrita_d2898881") },
                  { value: "guarded", label: t("generated.controlPlane.protegido_88789311"), description: t("generated.controlPlane.acoes_de_escrita_requerem_confirmacao_0dc05a33") },
                  { value: "supervised", label: t("generated.controlPlane.supervisionado_98065139"), description: t("generated.controlPlane.agente_pede_aprovacao_antes_de_executar_9c138356") },
                  { value: "escalation_required", label: t("generated.controlPlane.escalacao_obrigatoria_f4ae367e"), description: t("generated.controlPlane.todas_as_acoes_devem_ser_escaladas_321feb09") },
                ]}
              />
              <FormSelect
                label={t("generated.controlPlane.nivel_de_autonomia_514adb97")}
                value={autonomyPolicy.default_autonomy_tier}
                onChange={(event) =>
                  updateAutonomyPolicy({
                    default_autonomy_tier: event.target.value,
                  })
                }
                options={[
                  { value: "t0", label: "T0 — " + t("generated.controlPlane.minima_6ff54321"), description: t("generated.controlPlane.sem_acoes_autonomas_1f5759f6") },
                  { value: "t1", label: "T1 — " + t("generated.controlPlane.moderada_eded54a8"), description: t("generated.controlPlane.acoes_de_leitura_livres_0e837db1") },
                  { value: "t2", label: "T2 — " + t("generated.controlPlane.ampla_5afb3c7d"), description: t("generated.controlPlane.execucao_autonoma_com_guardrails_d40c3b1d") },
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
              <SectionCollapsible title={t("generated.controlPlane.campos_avancados_d4c87707")}>
                <div className="flex flex-col gap-6 pt-2">
                  <ListEditorField
                    label={t("generated.controlPlane.outcomes_principais_fa46d564")}
                    items={missionProfile.primary_outcomes}
                    onChange={(items) =>
                      updateMissionProfile({ primary_outcomes: items })
                    }
                    placeholder={t("generated.controlPlane.ex_reduzir_tempo_de_triagem_44f33c25")}
                  />
                  <ListEditorField
                    label={t("generated.controlPlane.success_metrics_7e2bf38d")}
                    description={t("generated.controlPlane.indicadores_usados_para_medir_se_o_agente_es_4929e9f4")}
                    items={missionProfile.kpis}
                    onChange={(items) => updateMissionProfile({ kpis: items })}
                    placeholder={t("generated.controlPlane.ex_acuracia_lead_time_cobertura_de_fontes_4d31cd23")}
                  />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormInput
                      label={t("generated.controlPlane.politica_de_citacao_704d9a58")}
                      value={responsePolicy.citation_policy}
                      onChange={(event) =>
                        updateResponsePolicy({ citation_policy: event.target.value })
                      }
                      placeholder={t("generated.controlPlane.ex_citar_label_e_data_quando_grounded_76a22d7c")}
                    />
                    <FormInput
                      label={t("generated.controlPlane.politica_de_fontes_5c9ba4d3")}
                      value={responsePolicy.source_policy}
                      onChange={(event) =>
                        updateResponsePolicy({ source_policy: event.target.value })
                      }
                      placeholder={t("generated.controlPlane.ex_preferir_knowledge_canonico_e_runbooks_989b24a3")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={t("generated.controlPlane.workflow_padrao_fd4702f7")}
                      items={operatingInstructions.default_workflow}
                      onChange={(items) =>
                        updateOperatingInstructions({ default_workflow: items })
                      }
                      placeholder={t("generated.controlPlane.ex_entender_buscar_grounding_agir_verificar_efc75c73")}
                    />
                    <ListEditorField
                      label={t("generated.controlPlane.heuristicas_de_execucao_6f902a60")}
                      items={operatingInstructions.execution_heuristics}
                      onChange={(items) =>
                        updateOperatingInstructions({ execution_heuristics: items })
                      }
                      placeholder={t("generated.controlPlane.ex_usar_modelo_menor_para_triagem_b9311764")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={t("generated.controlPlane.criterios_de_sucesso_75be6ba3")}
                      items={operatingInstructions.success_criteria}
                      onChange={(items) =>
                        updateOperatingInstructions({ success_criteria: items })
                      }
                      placeholder={t("generated.controlPlane.ex_resposta_correta_segura_e_verificavel_b6afecd0")}
                    />
                    <ListEditorField
                      label={t("generated.controlPlane.expectativas_de_handoff_cbe57fe5")}
                      items={operatingInstructions.handoff_expectations}
                      onChange={(items) =>
                        updateOperatingInstructions({ handoff_expectations: items })
                      }
                      placeholder={t("generated.controlPlane.ex_escalar_com_contexto_e_proxima_acao_suger_f3fc665a")}
                    />
                  </div>
                  <ListEditorField
                    label={t("generated.controlPlane.requisitos_de_aprovacao_28c6e8b2")}
                    items={hardRules.approval_requirements}
                    onChange={(items) =>
                      updateHardRules({ approval_requirements: items })
                    }
                    placeholder={t("generated.controlPlane.ex_producao_exige_confirmacao_humana_c46cd54e")}
                  />
                  <ListEditorField
                    label={t("generated.controlPlane.regras_inviolaveis_legado_7db0714d")}
                    description={t("generated.controlPlane.conteudo_redundante_com_rules_md_prefira_o_b_794e8aa8")}
                    items={hardRules.non_negotiables}
                    onChange={(items) =>
                      updateHardRules({ non_negotiables: items })
                    }
                    placeholder={t("generated.controlPlane.ex_nao_inventar_fatos_faa9fc09")}
                  />
                  <ListEditorField
                    label={t("generated.controlPlane.acoes_proibidas_legado_74f1a447")}
                    description={t("generated.controlPlane.conteudo_redundante_com_rules_md_prefira_o_b_794e8aa8")}
                    items={hardRules.forbidden_actions}
                    onChange={(items) =>
                      updateHardRules({ forbidden_actions: items })
                    }
                    placeholder={t("generated.controlPlane.ex_deploy_sem_aprovacao_explicita_b03285e7")}
                  />
                  <ListEditorField
                    label={t("generated.controlPlane.regras_de_seguranca_legado_c2205a39")}
                    description={t("generated.controlPlane.conteudo_redundante_com_rules_md_prefira_o_b_794e8aa8")}
                    items={hardRules.security_rules}
                    onChange={(items) =>
                      updateHardRules({ security_rules: items })
                    }
                    placeholder={t("generated.controlPlane.ex_nao_expor_segredos_ou_pii_06252b4f")}
                  />
                </div>
              </SectionCollapsible>

              <SectionCollapsible title={t("generated.controlPlane.overrides_avancados_de_prompt_e_autonomia_709e6550")}>
                <div className="flex flex-col gap-6 pt-2">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <FormInput
                      label={t("generated.controlPlane.funcao_profissional_95a3e77b")}
                      description={t("generated.controlPlane.campo_legado_prefira_descrever_o_papel_em_id_b4da655f")}
                      value={missionProfile.role}
                      onChange={(event) =>
                        updateMissionProfile({ role: event.target.value })
                      }
                      placeholder={t("generated.controlPlane.ex_sre_autonomo_supervisionado_447f36e1")}
                    />
                    <FormInput
                      label={t("generated.controlPlane.persona_45d338e4")}
                      value={interactionStyle.persona}
                      onChange={(event) =>
                        updateInteractionStyle({ persona: event.target.value })
                      }
                      placeholder={t("generated.controlPlane.ex_funcionario_tecnico_confiavel_02d336db")}
                    />
                  </div>
                  <MarkdownEditorField
                    label={t("generated.controlPlane.audiencia_e_contexto_legado_6ba304d8")}
                    value={missionProfile.audience}
                    onChange={(value) => updateMissionProfile({ audience: value })}
                    minHeight="160px"
                    placeholder={t("generated.controlPlane.descreva_o_publico_o_tipo_de_tarefa_restrico_38d51ab0")}
                  />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <FormSelect
                      label={t("generated.controlPlane.tom_11494f87")}
                      value={interactionStyle.tone}
                      onChange={(event) =>
                        updateInteractionStyle({ tone: event.target.value })
                      }
                      options={[
                        { value: "profissional", label: t("generated.controlPlane.profissional_df864169") },
                        { value: "calmo", label: t("generated.controlPlane.calmo_2768b8d5") },
                        { value: "direto", label: t("generated.controlPlane.direto_e8d58457") },
                        { value: "colaborativo", label: t("generated.controlPlane.colaborativo_63af6e00") },
                      ]}
                    />
                    <FormSelect
                      label={t("generated.controlPlane.modo_de_colaboracao_86d0fec7")}
                      value={interactionStyle.collaboration_style}
                      onChange={(event) =>
                        updateInteractionStyle({
                          collaboration_style: event.target.value,
                        })
                      }
                      options={[
                        { value: "colaborativo", label: t("generated.controlPlane.colaborativo_63af6e00") },
                        { value: "executor", label: t("generated.controlPlane.executor_52c5a39f") },
                        { value: "consultivo", label: t("generated.controlPlane.consultivo_a45ca9f4") },
                        { value: "investigativo", label: t("generated.controlPlane.investigativo_bdcf7850") },
                      ]}
                    />
                    <FormInput
                      label={t("generated.controlPlane.estilo_de_escalacao_e8248803")}
                      value={interactionStyle.escalation_style}
                      onChange={(event) =>
                        updateInteractionStyle({ escalation_style: event.target.value })
                      }
                      placeholder={t("generated.controlPlane.ex_escalar_com_contexto_e_proposta_039114d3")}
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <ListEditorField
                      label={t("generated.controlPlane.valores_f21528b8")}
                      items={interactionStyle.values}
                      onChange={(items) => updateInteractionStyle({ values: items })}
                      placeholder={t("generated.controlPlane.ex_honestidade_grounding_ownership_af00b0ff")}
                    />
                    <div className="flex flex-col gap-4">
                      <FormInput
                        label={t("generated.controlPlane.estilo_de_escrita_30c62094")}
                        value={interactionStyle.writing_style}
                        onChange={(event) =>
                          updateInteractionStyle({ writing_style: event.target.value })
                        }
                        placeholder={t("generated.controlPlane.ex_conciso_objetivo_e_rastreavel_1e0c183e")}
                      />
                      <ListEditorField
                        label={t("generated.controlPlane.responsibility_limits_legacy_b1df31a1")}
                        items={missionProfile.responsibility_limits}
                        onChange={(items) =>
                          updateMissionProfile({ responsibility_limits: items })
                        }
                        placeholder={t("generated.controlPlane.ex_nao_aprovar_deploy_em_producao_3b56a804")}
                      />
                    </div>
                  </div>
                  <JsonEditorField
                    label={t("generated.controlPlane.autonomy_policy_json_7a22dcef")}
                    description={t("generated.controlPlane.schema_canonico_completo_de_autonomia_inclui_179881e3")}
                    value={state.autonomyPolicyJson}
                    onChange={(value) =>
                      updateAgentSpecField("autonomyPolicyJson", value)
                    }
                  />
                  <JsonEditorField
                    label={t("generated.controlPlane.execution_policy_json_6d98304c")}
                    description={t("generated.controlPlane.politica_central_de_execucao_e_fator_humano__90084388")}
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
