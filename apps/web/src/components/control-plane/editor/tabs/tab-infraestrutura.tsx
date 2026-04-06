"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { LocalizedTree } from "@/components/shared/localized-tree";
import {
  FormInput,
} from "@/components/control-plane/shared/form-field";
import {
  buildBotMetadataPayload,
  buildAgentSpecPayload,
  parseJsonObject,
} from "@/lib/control-plane-editor";

/* -------------------------------------------------------------------------- */
/*  Request helper                                                             */
/* -------------------------------------------------------------------------- */

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

const SECTION_KEYS = [
  "general",
  "appearance",
  "identity",
  "prompting",
  "providers",
  "tools",
  "integrations",
  "memory",
  "knowledge",
  "runtime",
  "scheduler",
] as const;

/* -------------------------------------------------------------------------- */
/*  Tab: Infraestrutura                                                        */
/* -------------------------------------------------------------------------- */

export function TabInfraestrutura() {
  const {
    state,
    updateField,
    updateAgentSpecField,
    updateSectionJson,
    resetDirty,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const botId = state.bot.id;

  async function handleSave() {
    setBusyKey("save");
    try {
      // 1. Metadata (PATCH)
      const metaPayload = buildBotMetadataPayload({
        displayName: state.displayName,
        status: state.status,
        storageNamespace: state.storageNamespace,
        workspaceId: state.workspaceId,
        squadId: state.squadId,
        color: state.color,
        colorRgb: state.colorRgb,
        healthPort: state.healthPort,
        healthUrl: state.healthUrl,
        runtimeBaseUrl: state.runtimeBaseUrl,
        appearanceJson: state.appearanceJson,
        runtimeEndpointJson: state.runtimeEndpointJson,
        metadataJson: state.metadataJson,
      });

      const metaPromise = requestJson(`/api/control-plane/agents/${botId}`, {
        method: "PATCH",
        body: JSON.stringify(metaPayload),
      });

      // 2. Agent spec (PUT)
      const agentSpecPayload = buildAgentSpecPayload({
        missionProfileJson: state.missionProfileJson,
        interactionStyleJson: state.interactionStyleJson,
        operatingInstructionsJson: state.operatingInstructionsJson,
        hardRulesJson: state.hardRulesJson,
        responsePolicyJson: state.responsePolicyJson,
        modelPolicyJson: state.modelPolicyJson,
        toolPolicyJson: state.toolPolicyJson,
        memoryPolicyJson: state.memoryPolicyJson,
        knowledgePolicyJson: state.knowledgePolicyJson,
        autonomyPolicyJson: state.autonomyPolicyJson,
        executionPolicyJson: state.executionPolicyJson,
        resourceAccessPolicyJson: state.resourceAccessPolicyJson,
        voicePolicyJson: state.voicePolicyJson,
        imageAnalysisPolicyJson: state.imageAnalysisPolicyJson,
        memoryExtractionSchemaJson: state.memoryExtractionSchemaJson,
        skillPolicyJson: state.skillPolicyJson,
        customSkillsJson: state.customSkillsJson,
      });

      const specPromise = requestJson(
        `/api/control-plane/agents/${botId}/agent-spec`,
        {
          method: "PUT",
          body: JSON.stringify(agentSpecPayload),
        },
      );

      // 3. Sections (PUT each)
      const sectionsObj = parseJsonObject("Sections JSON", state.sectionsJson);
      const sectionPromises = SECTION_KEYS.map((key) => {
        const sectionData = sectionsObj[key] ?? {};
        return requestJson(
          `/api/control-plane/agents/${botId}/sections/${key}`,
          {
            method: "PUT",
            body: JSON.stringify(sectionData),
          },
        );
      });

      await Promise.all([metaPromise, specPromise, ...sectionPromises]);

      resetDirty("meta");
      resetDirty("agentSpec");
      resetDirty("sections");
      showToast(tl("Infraestrutura salva com sucesso."), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar infraestrutura."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <LocalizedTree>
      <div className="glass-card p-6 flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Infraestrutura
        </h2>
        <p className="text-sm text-[var(--text-tertiary)]">
          Configuracao tecnica — endpoints, policies e sections.
        </p>
      </div>

      {/* Connection fields */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <FormInput
          label="Health Port"
          description="Porta de health check (1-65535)."
          type="number"
          value={state.healthPort}
          onChange={(e) => updateField("healthPort", e.target.value)}
          placeholder="8080"
        />

        <FormInput
          label="Health URL"
          description="URL do endpoint de health."
          type="url"
          value={state.healthUrl}
          onChange={(e) => updateField("healthUrl", e.target.value)}
          placeholder="https://..."
        />

        <FormInput
          label="Runtime Base URL"
          description="URL base do runtime."
          type="url"
          value={state.runtimeBaseUrl}
          onChange={(e) => updateField("runtimeBaseUrl", e.target.value)}
          placeholder="https://..."
        />
      </div>

      {/* Advanced JSON */}
      <SectionCollapsible title="JSON avancado">
        <div className="flex flex-col gap-6">
          <JsonEditorField
            label="Appearance JSON"
            description="Configuracao visual completa."
            value={state.appearanceJson}
            onChange={(v) => updateField("appearanceJson", v)}
          />

          <JsonEditorField
            label="Runtime Endpoint JSON"
            description="Configuracao de endpoint do runtime."
            value={state.runtimeEndpointJson}
            onChange={(v) => updateField("runtimeEndpointJson", v)}
          />

          <JsonEditorField
            label="Metadata JSON"
            description="Metadados adicionais."
            value={state.metadataJson}
            onChange={(v) => updateField("metadataJson", v)}
          />
        </div>
      </SectionCollapsible>

      {/* Model, tool, voice, image policies */}
      <div className="flex flex-col gap-6">
        <JsonEditorField
          label="Model Policy"
          description="Configuracao do modelo (provider, temperature, etc)."
          value={state.modelPolicyJson}
          onChange={(v) => updateAgentSpecField("modelPolicyJson", v)}
        />

        <JsonEditorField
          label="Tool Policy"
          description="Ferramentas permitidas e configuracoes."
          value={state.toolPolicyJson}
          onChange={(v) => updateAgentSpecField("toolPolicyJson", v)}
        />

        <JsonEditorField
          label="Voice Policy"
          description="Configuracao de voz (TTS/STT)."
          value={state.voicePolicyJson}
          onChange={(v) => updateAgentSpecField("voicePolicyJson", v)}
        />

        <JsonEditorField
          label="Image Analysis Policy"
          description="Configuracao de analise de imagem."
          value={state.imageAnalysisPolicyJson}
          onChange={(v) => updateAgentSpecField("imageAnalysisPolicyJson", v)}
        />
      </div>

      {/* Section overrides */}
      <SectionCollapsible title="Section overrides">
        <div className="flex flex-col gap-3">
          <p className="text-xs text-[var(--text-quaternary)]">
            Todas as {SECTION_KEYS.length} sections em um unico JSON:{" "}
            {SECTION_KEYS.join(", ")}
          </p>
          <JsonEditorField
            label="Sections JSON"
            description="Override completo de todas as sections."
            value={state.sectionsJson}
            onChange={(v) => updateSectionJson(v)}
            minHeight="320px"
          />
        </div>
      </SectionCollapsible>

      {/* Save */}
      <div className="flex items-center justify-end gap-3 pt-2 border-t border-[var(--border-subtle)]">
        {(state.dirty.meta ||
          state.dirty.agentSpec ||
          state.dirty.sections) && (
          <span className="text-xs text-[var(--tone-warning-text)]">
            Alteracoes nao salvas
          </span>
        )}
        <button
          type="button"
          className="button-shell button-shell--primary"
          disabled={busyKey !== null}
          onClick={handleSave}
        >
          <span>
            {busyKey === "save" ? "Salvando..." : "Salvar infraestrutura"}
          </span>
        </button>
      </div>
      </div>
    </LocalizedTree>
  );
}
