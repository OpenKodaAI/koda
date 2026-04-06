"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { InheritedPromptPreview } from "@/components/control-plane/shared/inherited-context";
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

const DOCUMENT_FIELDS = [
  "system_prompt_md",
  "instructions_md",
  "rules_md",
] as const;

/* -------------------------------------------------------------------------- */
/*  Tab: Comportamento                                                         */
/* -------------------------------------------------------------------------- */

export function TabComportamento() {
  const {
    state,
    inherited,
    updateDocument,
    updateAgentSpecField,
    resetDirty,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const botId = state.bot.id;
  const workspacePrompt = inherited.workspaceSystemPrompt;
  const squadPrompt = inherited.squadSystemPrompt;

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
      showToast(tl("Comportamento salvo com sucesso."), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar comportamento."),
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
          Comportamento
        </h2>
        <p className="text-sm text-[var(--text-tertiary)]">
          Como o bot funciona — prompts de sistema, instrucoes e regras.
        </p>
      </div>

      {/* System prompt */}
      <MarkdownEditorField
        label="System Prompt (system_prompt_md)"
        description="Prompt de sistema principal."
        value={state.documents["system_prompt_md"] ?? ""}
        onChange={(v) => updateDocument("system_prompt_md", v)}
        minHeight="300px"
      />

      {/* Instructions */}
      <MarkdownEditorField
        label="Instructions (instructions_md)"
        description="Instrucoes detalhadas de operacao."
        value={state.documents["instructions_md"] ?? ""}
        onChange={(v) => updateDocument("instructions_md", v)}
        minHeight="300px"
      />

      {/* Rules */}
      <MarkdownEditorField
        label="Rules (rules_md)"
        description="Regras e restricoes de comportamento."
        value={state.documents["rules_md"] ?? ""}
        onChange={(v) => updateDocument("rules_md", v)}
        minHeight="180px"
      />

      {(workspacePrompt || squadPrompt) && (
        <section className="flex flex-col gap-4 rounded-[28px] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.015))] px-5 py-5">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
              {tl("Contexto herdado")}
            </span>
            <p className="text-sm leading-6 text-[var(--text-tertiary)]">
              {tl("O prompt final do agente agrega automaticamente as definicoes do espaco de trabalho e do time antes das instrucoes locais do bot.")}
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <InheritedPromptPreview
              source="workspace"
              label={tl("System prompt do espaco de trabalho")}
              value={workspacePrompt}
            />
            <InheritedPromptPreview
              source="squad"
              label={tl("System prompt do time")}
              value={squadPrompt}
            />
          </div>
        </section>
      )}

      {/* Advanced policies */}
      <SectionCollapsible title="Politicas avancadas">
        <div className="flex flex-col gap-6">
          <JsonEditorField
            label="Operating Instructions"
            description="Instrucoes operacionais em JSON."
            value={state.operatingInstructionsJson}
            onChange={(v) =>
              updateAgentSpecField("operatingInstructionsJson", v)
            }
          />

          <JsonEditorField
            label="Hard Rules"
            description="Regras inviolaveis em JSON."
            value={state.hardRulesJson}
            onChange={(v) => updateAgentSpecField("hardRulesJson", v)}
          />

          <JsonEditorField
            label="Response Policy"
            description="Politica de resposta em JSON."
            value={state.responsePolicyJson}
            onChange={(v) => updateAgentSpecField("responsePolicyJson", v)}
          />

          <JsonEditorField
            label="Autonomy Policy"
            description="Politica de autonomia em JSON."
            value={state.autonomyPolicyJson}
            onChange={(v) => updateAgentSpecField("autonomyPolicyJson", v)}
          />
        </div>
      </SectionCollapsible>

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
            {busyKey === "save" ? "Salvando..." : "Salvar comportamento"}
          </span>
        </button>
      </div>
      </div>
    </LocalizedTree>
  );
}
