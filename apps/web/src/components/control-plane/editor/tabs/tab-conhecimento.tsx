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

/* -------------------------------------------------------------------------- */
/*  Tab: Conhecimento (simplified)                                             */
/* -------------------------------------------------------------------------- */

export function TabConhecimento() {
  const {
    core,
    state,
    updateDocument,
    updateAgentSpecField,
  } = useAgentEditor();
  const { tl } = useAppI18n();

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
        title={tl("Conhecimento")}
        icon={BookOpen}
        dirty={state.dirty.agentSpec}
        defaultOpen
        variant="flat"
      >
        <ToggleField
          label={tl("Conhecimento ativo")}
          description={tl("Habilita memoria persistente e grounding automatico de conhecimento para este agente.")}
          checked={knowledgeEnabled}
          onChange={handleToggleKnowledge}
        />

        <ModelSelector
          label={tl("Modelo de extracao")}
          description={tl("Modelo usado para extrair aprendizados e memoria de cada turno.")}
          value={currentExtractionValue}
          onChange={handleExtractionModelChange}
          providers={providerEntries}
          enabledProviders={enabledProviders}
          emptyLabel="Herdar do modelo principal"
        />

        <MarkdownEditorField
          label={tl("Prompt de extracao")}
          description={tl("Instrucoes para guiar a extracao de memoria e aprendizados do agente.")}
          value={state.documents.memory_extraction_prompt_md ?? ""}
          onChange={(value) => updateDocument("memory_extraction_prompt_md", value)}
          minHeight="220px"
        />
      </PolicyCard>
    </div>
  );
}
