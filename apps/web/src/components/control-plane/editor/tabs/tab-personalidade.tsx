"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { LocalizedTree } from "@/components/shared/localized-tree";
import { buildAgentSpecPayload } from "@/lib/control-plane-editor";

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

const DOCUMENT_FIELDS = ["identity_md", "soul_md", "voice_prompt_md"] as const;

/* -------------------------------------------------------------------------- */
/*  Tab: Personalidade                                                         */
/* -------------------------------------------------------------------------- */

export function TabPersonalidade() {
  const {
    state,
    updateDocument,
    updateAgentSpecField,
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
      // 1. Save documents in parallel
      const docPromises = DOCUMENT_FIELDS.map((key) =>
        requestJson(`/api/control-plane/agents/${botId}/documents/${key}`, {
          method: "PUT",
          body: JSON.stringify({ content: state.documents[key] ?? "" }),
        }),
      );

      // 2. Save agent spec
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
      });

      const specPromise = requestJson(
        `/api/control-plane/agents/${botId}/agent-spec`,
        {
          method: "PUT",
          body: JSON.stringify(agentSpecPayload),
        },
      );

      await Promise.all([...docPromises, specPromise]);

      resetDirty("documents");
      resetDirty("agentSpec");
      showToast(tl("Personalidade salva com sucesso."), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar personalidade."),
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
          Personalidade
        </h2>
        <p className="text-sm text-[var(--text-tertiary)]">
          Carater e alma do bot — defina quem ele e e como se expressa.
        </p>
      </div>

      {/* Identity document */}
      <MarkdownEditorField
        label="Identity (identity_md)"
        description="Documento principal de identidade do bot."
        value={state.documents["identity_md"] ?? ""}
        onChange={(v) => updateDocument("identity_md", v)}
        minHeight="300px"
      />

      {/* Soul document */}
      <MarkdownEditorField
        label="Soul (soul_md)"
        description="Personalidade profunda, valores e principios."
        value={state.documents["soul_md"] ?? ""}
        onChange={(v) => updateDocument("soul_md", v)}
        minHeight="300px"
      />

      {/* Voice prompt */}
      <MarkdownEditorField
        label="Voice Prompt (voice_prompt_md)"
        description="Tom de voz, estilo de escrita e vocabulario."
        value={state.documents["voice_prompt_md"] ?? ""}
        onChange={(v) => updateDocument("voice_prompt_md", v)}
        minHeight="180px"
      />

      {/* Mission profile JSON */}
      <JsonEditorField
        label="Mission Profile"
        description="Objetivo e missao do bot em JSON."
        value={state.missionProfileJson}
        onChange={(v) => updateAgentSpecField("missionProfileJson", v)}
      />

      {/* Interaction style JSON */}
      <JsonEditorField
        label="Interaction Style"
        description="Estilo de interacao e comportamento conversacional."
        value={state.interactionStyleJson}
        onChange={(v) => updateAgentSpecField("interactionStyleJson", v)}
      />

      {/* Save */}
      <div className="flex items-center justify-end gap-3 pt-2 border-t border-[var(--border-subtle)]">
        {(state.dirty.documents || state.dirty.agentSpec) && (
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
            {busyKey === "save" ? "Salvando..." : "Salvar personalidade"}
          </span>
        </button>
      </div>
      </div>
    </LocalizedTree>
  );
}
