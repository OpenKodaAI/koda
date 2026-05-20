"use client";

import { useMemo } from "react";
import { BookOpen } from "lucide-react";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { ModelSelector } from "@/components/control-plane/shared/model-selector";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  parseKnowledgePolicy,
  parseMemoryPolicy,
  serializeKnowledgePolicy,
  serializeMemoryPolicy,
} from "@/lib/policy-serializers";

/*  Tab: Conhecimento (simplified)                                             */

export function TabConhecimento() {
  const {
    core,
    state,
    updateDocument,
    updateAgentSpecField,
  } = useAgentEditor();
  const { t } = useAppI18n();

  const memoryPolicy = useMemo(
    () => parseMemoryPolicy(state.memoryPolicyJson),
    [state.memoryPolicyJson],
  );
  const knowledgePolicy = useMemo(
    () => parseKnowledgePolicy(state.knowledgePolicyJson),
    [state.knowledgePolicyJson],
  );

  /* ---- Build extraction model options from agent's provider -------- */
  const providerEntries = useMemo(
    () => core.providers.providers ?? {},
    [core.providers.providers],
  );
  const enabledProviders = useMemo(() => {
    const configured = Array.isArray(core.providers.enabled_providers)
      ? core.providers.enabled_providers.map(String)
      : [];
    if (configured.length > 0) return configured;
    return Object.entries(providerEntries)
      .filter(([, payload]) => Boolean(payload.enabled))
      .map(([provider]) => provider);
  }, [core.providers.enabled_providers, providerEntries]);

  const currentExtractionValue = memoryPolicy.extraction_provider && memoryPolicy.extraction_model
    ? `${memoryPolicy.extraction_provider}:${memoryPolicy.extraction_model}`
    : "";

  /* ---- Knowledge enabled = both memory + knowledge grounding on ---- */
  const knowledgeEnabled = knowledgePolicy.enabled;

  function handleToggleKnowledge(enabled: boolean) {
    /* Toggle knowledge grounding with quality defaults */
    const nextKnowledge = { ...knowledgePolicy, enabled };
    if (enabled) {
      nextKnowledge.require_owner_provenance = true;
      nextKnowledge.require_freshness_provenance = true;
    }
    updateAgentSpecField(
      "knowledgePolicyJson",
      serializeKnowledgePolicy(nextKnowledge),
    );
    /* Keep memory in sync with quality defaults */
    const nextMemory = { ...memoryPolicy, enabled };
    if (enabled) {
      nextMemory.proactive_enabled = true;
      nextMemory.procedural_enabled = true;
      nextMemory.maintenance_enabled = true;
      nextMemory.digest_enabled = true;
      nextMemory.observed_pattern_requires_review = true;
    }
    updateAgentSpecField(
      "memoryPolicyJson",
      serializeMemoryPolicy(nextMemory),
    );
  }

  function handleExtractionModelChange(combined: string) {
    if (!combined) {
      updateAgentSpecField(
        "memoryPolicyJson",
        serializeMemoryPolicy({
          ...memoryPolicy,
          extraction_provider: "",
          extraction_model: "",
        }),
      );
      return;
    }
    const [providerId, ...modelParts] = combined.split(":");
    updateAgentSpecField(
      "memoryPolicyJson",
      serializeMemoryPolicy({
        ...memoryPolicy,
        extraction_provider: providerId,
        extraction_model: modelParts.join(":"),
      }),
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PolicyCard
        title={t("generated.controlPlane.conhecimento_d1f8a9d1")}
        icon={BookOpen}
        dirty={state.dirty.agentSpec}
        defaultOpen
        variant="flat"
      >
        <ToggleField
          label={t("generated.controlPlane.conhecimento_ativo_d7bd2014")}
          description={t("generated.controlPlane.habilita_memoria_persistente_e_grounding_aut_8c1c2db9")}
          checked={knowledgeEnabled}
          onChange={handleToggleKnowledge}
        />

        <ModelSelector
          label={t("generated.controlPlane.modelo_de_extracao_19567fe2")}
          description={t("generated.controlPlane.modelo_usado_para_extrair_aprendizados_e_mem_466753f8")}
          value={currentExtractionValue}
          onChange={handleExtractionModelChange}
          providers={providerEntries}
          enabledProviders={enabledProviders}
          emptyLabel={t("generated.controlPlane.herdar_do_modelo_principal_16253e7c")}
        />

        <MarkdownEditorField
          label={t("generated.controlPlane.prompt_de_extracao_94182bf9")}
          description={t("generated.controlPlane.instrucoes_para_guiar_a_extracao_de_memoria__e137f6b7")}
          value={state.documents.memory_extraction_prompt_md ?? ""}
          onChange={(value) => updateDocument("memory_extraction_prompt_md", value)}
          minHeight="220px"
        />
      </PolicyCard>
    </div>
  );
}
