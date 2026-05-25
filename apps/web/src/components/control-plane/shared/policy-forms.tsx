"use client";

import { CheckboxGroupField } from "@/components/control-plane/shared/checkbox-group-field";
import { FormInput, FormSelect } from "@/components/control-plane/shared/form-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { TagInputField } from "@/components/control-plane/shared/tag-input-field";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  AutonomyPolicyData,
  KnowledgePolicyData,
  MemoryPolicyData,
} from "@/lib/policy-serializers";

function parseNumberInput(value: string, fallback: number) {
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function ToggleCard({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] px-4 py-1">
      <ToggleField
        label={label}
        description={description}
        checked={checked}
        onChange={onChange}
      />
    </div>
  );
}

export function MemoryPolicyForm({
  policy,
  onChange,
  providerOptions,
}: {
  policy: MemoryPolicyData;
  onChange: (next: MemoryPolicyData) => void;
  providerOptions: Array<{ value: string; label: string }>;
}) {
  const { t } = useAppI18n();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.memoria_habilitada_72a98e34")}
            checked={policy.enabled}
            onChange={(checked) => onChange({ ...policy, enabled: checked })}
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.memoria_proativa_4cb243f6")}
            description={t("generated.controlPlane.permite_sugerir_contexto_util_antes_de_ser_s_c6c77ec1")}
            checked={policy.proactive_enabled}
            onChange={(checked) =>
              onChange({ ...policy, proactive_enabled: checked })
            }
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.memoria_procedural_ea2e2174")}
            description={t("generated.controlPlane.aprende_procedimentos_e_padroes_uteis_ao_lon_493f493b")}
            checked={policy.procedural_enabled}
            onChange={(checked) =>
              onChange({ ...policy, procedural_enabled: checked })
            }
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.auto_manutencao_ec0220d2")}
            description={t("generated.controlPlane.mantem_a_memoria_limpa_e_operacional_ao_long_dc0fd339")}
            checked={policy.maintenance_enabled}
            onChange={(checked) =>
              onChange({ ...policy, maintenance_enabled: checked })
            }
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <FormSelect
          label={t("generated.controlPlane.postura_de_risco_6cba15f2")}
          value={policy.risk_posture}
          onChange={(event) =>
            onChange({ ...policy, risk_posture: event.target.value })
          }
          options={[
            { value: "conservative", label: t("generated.controlPlane.conservadora_65d653e2") },
            { value: "balanced", label: t("generated.controlPlane.equilibrada_50b6b2cb") },
            { value: "aggressive", label: t("generated.controlPlane.agressiva_07421904") },
          ]}
        />
        <FormSelect
          label={t("generated.controlPlane.densidade_de_memoria_3681ba63")}
          value={policy.memory_density_target}
          onChange={(event) =>
            onChange({
              ...policy,
              memory_density_target: event.target.value,
            })
          }
          options={[
            { value: "sparse", label: t("generated.controlPlane.esparsa_c8b19ab7") },
            { value: "focused", label: t("generated.controlPlane.focada_da0681f7") },
            { value: "dense", label: t("generated.controlPlane.densa_ddc78dfd") },
          ]}
        />
        <FormInput
          label={t("generated.controlPlane.memorias_por_vez_d776eebc")}
          type="number"
          min="1"
          step="1"
          value={policy.max_recall.toString()}
          onChange={(event) =>
            onChange({
              ...policy,
              max_recall: parseNumberInput(event.target.value, policy.max_recall),
            })
          }
        />
        <FormInput
          label={t("generated.controlPlane.contexto_de_memoria_2f83edf7")}
          type="number"
          min="256"
          step="128"
          value={policy.max_context_tokens.toString()}
          onChange={(event) =>
            onChange({
              ...policy,
              max_context_tokens: parseNumberInput(
                event.target.value,
                policy.max_context_tokens,
              ),
            })
          }
        />
      </div>

      <SectionCollapsible title={t("generated.controlPlane.como_o_agente_aprende_e_o_que_vale_guardar_91a96adf")}>
        <div className="flex flex-col gap-5 pt-2">
          <div className="flex flex-wrap gap-3">
            <div className="min-w-[240px] flex-1">
              <ToggleCard
                label={t("generated.controlPlane.digest_de_memoria_9f016b69")}
                description={t("generated.controlPlane.consolida_aprendizados_recorrentes_em_resumo_3a69b830")}
                checked={policy.digest_enabled}
                onChange={(checked) =>
                  onChange({ ...policy, digest_enabled: checked })
                }
              />
            </div>
            <div className="min-w-[240px] flex-1">
              <ToggleCard
                label={t("generated.controlPlane.revisar_padroes_13888064")}
                description={t("generated.controlPlane.exige_revisao_antes_de_promover_padroes_obse_6eb4fd67")}
                checked={policy.observed_pattern_requires_review}
                onChange={(checked) =>
                  onChange({
                    ...policy,
                    observed_pattern_requires_review: checked,
                  })
                }
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <FormInput
              label={t("generated.controlPlane.itens_por_extracao_3eb04941")}
              type="number"
              min="1"
              step="1"
              value={policy.max_extraction_items.toString()}
              onChange={(event) =>
                onChange({
                  ...policy,
                  max_extraction_items: parseNumberInput(
                    event.target.value,
                    policy.max_extraction_items,
                  ),
                })
              }
            />
            <FormInput
              label={t("generated.controlPlane.maximo_por_usuario_dabe66fc")}
              type="number"
              min="1"
              step="1"
              value={policy.max_per_user.toString()}
              onChange={(event) =>
                onChange({
                  ...policy,
                  max_per_user: parseNumberInput(
                    event.target.value,
                    policy.max_per_user,
                  ),
                })
              }
            />
            <FormSelect
              label={t("generated.controlPlane.provider_de_extracao_8a7ea8b4")}
              description={t("generated.controlPlane.provider_usado_para_extrair_aprendizados_do__0f632bc7")}
              value={policy.extraction_provider}
              onChange={(event) =>
                onChange({ ...policy, extraction_provider: event.target.value })
              }
              options={[
                { value: "", label: t("generated.controlPlane.herdar_do_padrao_global_199d99a8") },
                ...providerOptions,
              ]}
            />
            <FormInput
              label={t("generated.controlPlane.modelo_de_extracao_03028047")}
              description={t("generated.controlPlane.modelo_especifico_usado_para_extrair_memoria_88df10a6")}
              value={policy.extraction_model}
              onChange={(event) =>
                onChange({ ...policy, extraction_model: event.target.value })
              }
              placeholder={t("generated.controlPlane.ex_claude_sonnet_4_6_48d6d69e")}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <TagInputField
              label={t("generated.controlPlane.dominios_de_foco_80ab825d")}
              description={t("generated.controlPlane.temas_nos_quais_o_agente_deve_investir_mais__46247ffb")}
              values={policy.focus_domains}
              onChange={(values) => onChange({ ...policy, focus_domains: values })}
              placeholder={t("generated.controlPlane.ex_incidentes_a0a0fe97")}
            />
            <TagInputField
              label={t("generated.controlPlane.camadas_preferidas_cf8d364a")}
              description={t("generated.controlPlane.camadas_de_memoria_com_mais_peso_quando_houv_4886567e")}
              values={policy.preferred_layers}
              onChange={(values) =>
                onChange({ ...policy, preferred_layers: values })
              }
              placeholder={t("generated.controlPlane.ex_procedural_84640812")}
            />
            <TagInputField
              label={t("generated.controlPlane.camadas_proibidas_para_acoes_600c854c")}
              description={t("generated.controlPlane.camadas_que_nao_devem_sustentar_acoes_sensiv_4dee8a9d")}
              values={policy.forbidden_layers_for_actions}
              onChange={(values) =>
                onChange({
                  ...policy,
                  forbidden_layers_for_actions: values,
                })
              }
              placeholder={t("generated.controlPlane.ex_proactive_6f631fc9")}
            />
          </div>
        </div>
      </SectionCollapsible>

      <SectionCollapsible title={t("generated.controlPlane.ajustes_avancados_de_ranking_e_recall_aa97be4f")}>
        <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 xl:grid-cols-3">
          <FormInput
            label={t("generated.controlPlane.similaridade_minima_03023546")}
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={policy.recall_threshold.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                recall_threshold: parseNumberInput(
                  event.target.value,
                  policy.recall_threshold,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.timeout_de_recall_0707b75b")}
            type="number"
            min="0.1"
            step="0.1"
            value={policy.recall_timeout.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                recall_timeout: parseNumberInput(
                  event.target.value,
                  policy.recall_timeout,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.recall_procedural_e2d14723")}
            type="number"
            min="1"
            step="1"
            value={policy.procedural_max_recall.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                procedural_max_recall: parseNumberInput(
                  event.target.value,
                  policy.procedural_max_recall,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.deduplicacao_semantica_0b49be65")}
            description={t("generated.controlPlane.threshold_para_evitar_memorias_semanticament_7501a226")}
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={policy.similarity_dedup_threshold.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                similarity_dedup_threshold: parseNumberInput(
                  event.target.value,
                  policy.similarity_dedup_threshold,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.half_life_dias_4cc40641")}
            description={t("generated.controlPlane.peso_de_recencia_aplicado_no_ranking_de_reca_f0cce4c3")}
            type="number"
            min="1"
            step="1"
            value={policy.recency_half_life_days.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                recency_half_life_days: parseNumberInput(
                  event.target.value,
                  policy.recency_half_life_days,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.promocao_apos_sucessos_e2168c27")}
            description={t("generated.controlPlane.minimo_de_sucessos_verificados_para_promover_0d49557a")}
            type="number"
            min="1"
            step="1"
            value={policy.minimum_verified_successes.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                minimum_verified_successes: parseNumberInput(
                  event.target.value,
                  policy.minimum_verified_successes,
                ),
              })
            }
          />
        </div>
      </SectionCollapsible>
    </div>
  );
}

export function KnowledgePolicyForm({
  policy,
  onChange,
  layerOptions,
}: {
  policy: KnowledgePolicyData;
  onChange: (next: KnowledgePolicyData) => void;
  layerOptions: Array<{ value: string; label: string }>;
}) {
  const { t } = useAppI18n();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.grounding_habilitado_bbc5f800")}
            checked={policy.enabled}
            onChange={(checked) => onChange({ ...policy, enabled: checked })}
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.exigir_owner_6ecbd756")}
            description={t("generated.controlPlane.bloqueia_fontes_criticas_sem_dono_definido_e145befb")}
            checked={policy.require_owner_provenance}
            onChange={(checked) =>
              onChange({
                ...policy,
                require_owner_provenance: checked,
              })
            }
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={t("generated.controlPlane.exigir_freshness_a9131edb")}
            description={t("generated.controlPlane.bloqueia_fontes_criticas_sem_janela_de_fresc_e82b4d68")}
            checked={policy.require_freshness_provenance}
            onChange={(checked) =>
              onChange({
                ...policy,
                require_freshness_provenance: checked,
              })
            }
          />
        </div>
      </div>

      <CheckboxGroupField
        label={t("generated.controlPlane.camadas_permitidas_568c3c57")}
        description={t("generated.controlPlane.escolha_em_quais_camadas_o_agente_pode_se_ap_ed5e3cc1")}
        options={layerOptions}
        selected={policy.allowed_layers}
        onChange={(selected) =>
          onChange({ ...policy, allowed_layers: selected })
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <FormInput
          label={t("generated.controlPlane.trechos_por_busca_02dccb85")}
          type="number"
          min="1"
          step="1"
          value={policy.max_results.toString()}
          onChange={(event) =>
            onChange({
              ...policy,
              max_results: parseNumberInput(
                event.target.value,
                policy.max_results,
              ),
            })
          }
        />
        <FormInput
          label={t("generated.controlPlane.contexto_de_conhecimento_4d80778d")}
          type="number"
          min="256"
          step="128"
          value={policy.context_max_tokens.toString()}
          onChange={(event) =>
            onChange({
              ...policy,
              context_max_tokens: parseNumberInput(
                event.target.value,
                policy.context_max_tokens,
              ),
            })
          }
        />
        <FormInput
          label={t("generated.controlPlane.idade_maxima_dias_3ee1c668")}
          type="number"
          min="1"
          step="1"
          value={policy.max_source_age_days.toString()}
          onChange={(event) =>
            onChange({
              ...policy,
              max_source_age_days: parseNumberInput(
                event.target.value,
                policy.max_source_age_days,
              ),
            })
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <TagInputField
          label={t("generated.controlPlane.arquivos_globais_incluidos_db1f7ed0")}
          description={t("generated.controlPlane.arquivos_globais_que_podem_entrar_na_indexac_0a26acf1")}
          values={policy.source_globs}
          onChange={(values) => onChange({ ...policy, source_globs: values })}
          placeholder={t("generated.controlPlane.ex_docs_md_1a7d15bc")}
        />
        <TagInputField
          label={t("generated.controlPlane.arquivos_do_workspace_incluidos_ea401b75")}
          description={t("generated.controlPlane.arquivos_dinamicos_elegiveis_dentro_do_works_66582270")}
          values={policy.workspace_source_globs}
          onChange={(values) =>
            onChange({ ...policy, workspace_source_globs: values })
          }
          placeholder={t("generated.controlPlane.ex_readme_md_cc7da155")}
        />
      </div>

      <SectionCollapsible title={t("generated.controlPlane.ajustes_avancados_de_recuperacao_4141992c")}>
        <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 xl:grid-cols-4">
          <FormInput
            label={t("generated.controlPlane.similaridade_minima_03023546")}
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={policy.recall_threshold.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                recall_threshold: parseNumberInput(
                  event.target.value,
                  policy.recall_threshold,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.timeout_de_recuperacao_f32cb1fd")}
            description={t("generated.controlPlane.tempo_maximo_de_recuperacao_antes_de_degrada_d840a6f1")}
            type="number"
            min="0.1"
            step="0.1"
            value={policy.recall_timeout.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                recall_timeout: parseNumberInput(
                  event.target.value,
                  policy.recall_timeout,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.arquivos_do_workspace_3f43ffea")}
            description={t("generated.controlPlane.maximo_de_arquivos_dinamicos_avaliados_por_b_ff7835d7")}
            type="number"
            min="0"
            step="1"
            value={policy.workspace_max_files.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                workspace_max_files: parseNumberInput(
                  event.target.value,
                  policy.workspace_max_files,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.padroes_observados_e3a11106")}
            description={t("generated.controlPlane.limite_de_padroes_semanticos_fracos_no_groun_2ee0e1f6")}
            type="number"
            min="0"
            step="1"
            value={policy.max_observed_patterns.toString()}
            onChange={(event) =>
              onChange({
                ...policy,
                max_observed_patterns: parseNumberInput(
                  event.target.value,
                  policy.max_observed_patterns,
                ),
              })
            }
          />
          <FormInput
            label={t("generated.controlPlane.modo_de_promocao_ff0cd1b9")}
            description={t("generated.controlPlane.hoje_a_promocao_continua_governada_por_fila__f81977b2")}
            value={policy.promotion_mode}
            readOnly
            disabled
          />
        </div>
      </SectionCollapsible>
    </div>
  );
}

/*  Simplified forms (normal mode)                                             */

export function MemoryPolicyFormSimple({
  policy,
  onChange,
}: {
  policy: MemoryPolicyData;
  onChange: (next: MemoryPolicyData) => void;
}) {
  const { t } = useAppI18n();

  function handleToggle(enabled: boolean) {
    const next = { ...policy, enabled };
    if (enabled) {
      next.proactive_enabled = true;
      next.procedural_enabled = true;
      next.maintenance_enabled = true;
      next.digest_enabled = true;
      next.observed_pattern_requires_review = true;
    }
    onChange(next);
  }

  return (
    <ToggleCard
      label={t("generated.controlPlane.memoria_habilitada_72a98e34")}
      description={t("generated.controlPlane.o_agente_retem_e_usa_aprendizados_entre_conv_1b50cb8f")}
      checked={policy.enabled}
      onChange={handleToggle}
    />
  );
}

export function KnowledgePolicyFormSimple({
  policy,
  memoryPolicy,
  onChange,
  onMemoryChange,
  providerOptions,
}: {
  policy: KnowledgePolicyData;
  memoryPolicy: MemoryPolicyData;
  onChange: (next: KnowledgePolicyData) => void;
  onMemoryChange: (next: MemoryPolicyData) => void;
  providerOptions: Array<{ value: string; label: string }>;
}) {
  const { t } = useAppI18n();

  function handleToggle(enabled: boolean) {
    const next = { ...policy, enabled };
    if (enabled) {
      next.require_owner_provenance = true;
      next.require_freshness_provenance = true;
    }
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-5">
      <ToggleCard
        label={t("generated.controlPlane.grounding_habilitado_bbc5f800")}
        description={t("generated.controlPlane.o_agente_busca_fontes_verificadas_antes_de_r_72c30f84")}
        checked={policy.enabled}
        onChange={handleToggle}
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FormSelect
          label={t("generated.controlPlane.provider_de_extracao_8a7ea8b4")}
          description={t("generated.controlPlane.provider_usado_para_extrair_aprendizados_ab6185d4")}
          value={memoryPolicy.extraction_provider}
          onChange={(event) =>
            onMemoryChange({ ...memoryPolicy, extraction_provider: event.target.value })
          }
          options={[
            { value: "", label: t("generated.controlPlane.herdar_do_padrao_global_199d99a8") },
            ...providerOptions,
          ]}
        />
        <FormInput
          label={t("generated.controlPlane.modelo_de_extracao_03028047")}
          description={t("generated.controlPlane.modelo_usado_para_extrair_memoria_47845826")}
          value={memoryPolicy.extraction_model}
          onChange={(event) =>
            onMemoryChange({ ...memoryPolicy, extraction_model: event.target.value })
          }
          placeholder={t("generated.controlPlane.ex_claude_sonnet_4_6_48d6d69e")}
        />
      </div>
    </div>
  );
}

export function AutonomyPolicyForm({
  policy,
  onChange,
  approvalOptions,
  tierOptions,
}: {
  policy: AutonomyPolicyData;
  onChange: (next: AutonomyPolicyData) => void;
  approvalOptions: Array<{ value: string; label: string }>;
  tierOptions: Array<{ value: string; label: string }>;
}) {
  const { t } = useAppI18n();
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <FormSelect
        label={t("generated.controlPlane.approval_mode_padrao_f9190465")}
        description={t("generated.controlPlane.nivel_de_contencao_padrao_para_execucoes_do__6120d5e2")}
        value={policy.default_approval_mode}
        onChange={(event) =>
          onChange({
            ...policy,
            default_approval_mode: event.target.value,
          })
        }
        options={approvalOptions}
      />
      <FormSelect
        label={t("generated.controlPlane.autonomy_tier_padrao_2be664e9")}
        description={t("generated.controlPlane.envelope_de_autonomia_padrao_para_tarefas_co_699f7c91")}
        value={policy.default_autonomy_tier}
        onChange={(event) =>
          onChange({
            ...policy,
            default_autonomy_tier: event.target.value,
          })
        }
        options={tierOptions}
      />
    </div>
  );
}
