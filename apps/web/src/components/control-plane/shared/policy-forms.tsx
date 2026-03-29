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
  description: string;
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
  const { tl } = useAppI18n();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Memória habilitada")}
            description={tl("Ativa recall e persistência de memória para o agente.")}
            checked={policy.enabled}
            onChange={(checked) => onChange({ ...policy, enabled: checked })}
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Memória proativa")}
            description={tl("Permite sugerir contexto útil antes de ser solicitado.")}
            checked={policy.proactive_enabled}
            onChange={(checked) =>
              onChange({ ...policy, proactive_enabled: checked })
            }
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Memória procedural")}
            description={tl("Aprende procedimentos e padrões úteis ao longo do uso.")}
            checked={policy.procedural_enabled}
            onChange={(checked) =>
              onChange({ ...policy, procedural_enabled: checked })
            }
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Auto manutenção")}
            description={tl("Mantém a memória limpa e operacional ao longo do tempo.")}
            checked={policy.maintenance_enabled}
            onChange={(checked) =>
              onChange({ ...policy, maintenance_enabled: checked })
            }
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <FormSelect
          label={tl("Postura de risco")}
          description={tl("Escolha o equilíbrio entre cautela e iniciativa ao usar memória.")}
          value={policy.risk_posture}
          onChange={(event) =>
            onChange({ ...policy, risk_posture: event.target.value })
          }
          options={[
            { value: "conservative", label: tl("Conservadora") },
            { value: "balanced", label: tl("Equilibrada") },
            { value: "aggressive", label: tl("Agressiva") },
          ]}
        />
        <FormSelect
          label={tl("Densidade de memória")}
          description={tl("Quanto contexto de memória tende a entrar por turno.")}
          value={policy.memory_density_target}
          onChange={(event) =>
            onChange({
              ...policy,
              memory_density_target: event.target.value,
            })
          }
          options={[
            { value: "sparse", label: tl("Esparsa") },
            { value: "focused", label: tl("Focada") },
            { value: "dense", label: tl("Densa") },
          ]}
        />
        <FormInput
          label={tl("Memórias por vez")}
          description={tl("Quantidade máxima de memórias trazidas em cada recall.")}
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
          label={tl("Contexto de memória")}
          description={tl("Orçamento máximo de contexto vindo da memória.")}
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

      <SectionCollapsible title={tl("Como o agente aprende e o que vale guardar")}>
        <div className="flex flex-col gap-5 pt-2">
          <div className="flex flex-wrap gap-3">
            <div className="min-w-[240px] flex-1">
              <ToggleCard
                label={tl("Digest de memória")}
                description={tl("Consolida aprendizados recorrentes em resumos úteis.")}
                checked={policy.digest_enabled}
                onChange={(checked) =>
                  onChange({ ...policy, digest_enabled: checked })
                }
              />
            </div>
            <div className="min-w-[240px] flex-1">
              <ToggleCard
                label={tl("Revisar padrões")}
                description={tl("Exige revisão antes de promover padrões observados.")}
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
              label={tl("Itens por extração")}
              description={tl("Máximo de itens que podem ser aprendidos em um único turno.")}
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
              label={tl("Máximo por usuário")}
              description={tl("Limite de memórias persistidas por usuário.")}
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
              label={tl("Provider de extração")}
              description={tl("Provider usado para extrair aprendizados do turno.")}
              value={policy.extraction_provider}
              onChange={(event) =>
                onChange({ ...policy, extraction_provider: event.target.value })
              }
              options={[
                { value: "", label: tl("Herdar do padrão global") },
                ...providerOptions,
              ]}
            />
            <FormInput
              label={tl("Modelo de extração")}
              description={tl("Modelo específico usado para extrair memória, se quiser fixar um.")}
              value={policy.extraction_model}
              onChange={(event) =>
                onChange({ ...policy, extraction_model: event.target.value })
              }
              placeholder={tl("Ex: claude-sonnet-4-6")}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <TagInputField
              label={tl("Domínios de foco")}
              description={tl("Temas nos quais o agente deve investir mais retenção.")}
              values={policy.focus_domains}
              onChange={(values) => onChange({ ...policy, focus_domains: values })}
              placeholder={tl("Ex: incidentes")}
            />
            <TagInputField
              label={tl("Camadas preferidas")}
              description={tl("Camadas de memória com mais peso quando houver empate.")}
              values={policy.preferred_layers}
              onChange={(values) =>
                onChange({ ...policy, preferred_layers: values })
              }
              placeholder={tl("Ex: procedural")}
            />
            <TagInputField
              label={tl("Camadas proibidas para ações")}
              description={tl("Camadas que não devem sustentar ações sensíveis sozinhas.")}
              values={policy.forbidden_layers_for_actions}
              onChange={(values) =>
                onChange({
                  ...policy,
                  forbidden_layers_for_actions: values,
                })
              }
              placeholder={tl("Ex: proactive")}
            />
          </div>
        </div>
      </SectionCollapsible>

      <SectionCollapsible title={tl("Ajustes avançados de ranking e recall")}>
        <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 xl:grid-cols-3">
          <FormInput
            label={tl("Similaridade mínima")}
            description={tl("Semelhança mínima para uma memória entrar no recall.")}
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
            label={tl("Timeout de recall")}
            description={tl("Tempo máximo da busca antes de desistir.")}
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
            label={tl("Recall procedural")}
            description={tl("Quantos procedimentos podem entrar por recall.")}
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
            label={tl("Deduplicação semântica")}
            description={tl("Threshold para evitar memórias semanticamente duplicadas.")}
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
            label={tl("Half-life (dias)")}
            description={tl("Peso de recência aplicado no ranking de recall.")}
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
            label={tl("Promoção após sucessos")}
            description={tl("Mínimo de sucessos verificados para promover um padrão.")}
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
  const { tl } = useAppI18n();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Grounding habilitado")}
            description={tl("Ativa grounding via recuperação de conhecimento.")}
            checked={policy.enabled}
            onChange={(checked) => onChange({ ...policy, enabled: checked })}
          />
        </div>
        <div className="min-w-[240px] flex-1">
          <ToggleCard
            label={tl("Exigir owner")}
            description={tl("Bloqueia fontes críticas sem dono definido.")}
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
            label={tl("Exigir freshness")}
            description={tl("Bloqueia fontes críticas sem janela de frescor definida.")}
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
        label={tl("Camadas permitidas")}
        description={tl("Escolha em quais camadas o agente pode se apoiar. Se estiver em dúvida, mantenha as camadas mais fortes marcadas.")}
        options={layerOptions}
        selected={policy.allowed_layers}
        onChange={(selected) =>
          onChange({ ...policy, allowed_layers: selected })
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <FormInput
          label={tl("Trechos por busca")}
          description={tl("Quantidade máxima de trechos trazidos pelo grounding.")}
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
          label={tl("Contexto de conhecimento")}
          description={tl("Orçamento máximo de contexto vindo do conhecimento.")}
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
          label={tl("Idade máxima (dias)")}
          description={tl("Idade máxima aceitável para fontes usadas no contexto.")}
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
          label={tl("Arquivos globais incluídos")}
          description={tl("Arquivos globais que podem entrar na indexação semântica.")}
          values={policy.source_globs}
          onChange={(values) => onChange({ ...policy, source_globs: values })}
          placeholder={tl("Ex: docs/**/*.md")}
        />
        <TagInputField
          label={tl("Arquivos do workspace incluídos")}
          description={tl("Arquivos dinâmicos elegíveis dentro do workspace do agente.")}
          values={policy.workspace_source_globs}
          onChange={(values) =>
            onChange({ ...policy, workspace_source_globs: values })
          }
          placeholder={tl("Ex: README.md")}
        />
      </div>

      <SectionCollapsible title={tl("Ajustes avançados de recuperação")}>
        <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 xl:grid-cols-4">
          <FormInput
            label={tl("Similaridade mínima")}
            description={tl("Similaridade mínima para um hit de conhecimento.")}
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
            label={tl("Timeout de recuperação")}
            description={tl("Tempo máximo de recuperação antes de degradar.")}
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
            label={tl("Arquivos do workspace")}
            description={tl("Máximo de arquivos dinâmicos avaliados por busca.")}
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
            label={tl("Padrões observados")}
            description={tl("Limite de padrões semânticos fracos no grounding.")}
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
            label={tl("Modo de promoção")}
            description={tl("Hoje a promoção continua governada por fila de revisão.")}
            value={policy.promotion_mode}
            readOnly
            disabled
          />
        </div>
      </SectionCollapsible>
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
  const { tl } = useAppI18n();
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <FormSelect
        label={tl("Approval mode padrão")}
        description={tl("Nível de contenção padrão para execuções do agente.")}
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
        label={tl("Autonomy tier padrão")}
        description={tl("Envelope de autonomia padrão para tarefas complexas.")}
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
