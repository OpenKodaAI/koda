"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { ColorPickerField } from "@/components/control-plane/shared/color-picker-field";
import { LocalizedTree } from "@/components/shared/localized-tree";
import {
  FormInput,
  FormSelect,
} from "@/components/control-plane/shared/form-field";
import { buildBotMetadataPayload } from "@/lib/control-plane-editor";

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
/*  Tab: Identidade                                                            */
/* -------------------------------------------------------------------------- */

export function TabIdentidade() {
  const { state, updateField, resetDirty } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const botId = state.bot.id;

  async function handleSave() {
    setBusyKey("save");
    try {
      const payload = buildBotMetadataPayload({
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

      await requestJson(`/api/control-plane/agents/${botId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });

      resetDirty("meta");
      showToast(tl("Identidade salva com sucesso."), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar identidade."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <LocalizedTree>
      <div className="glass-card p-6 flex flex-col gap-8">
      {/* Live orb preview */}
      <div className="flex justify-center py-4">
        <BotAgentGlyph
          botId={botId}
          color={state.color || "#8B8B93"}
          className="h-[72px] w-[72px] rounded-[1.15rem] bot-swatch--animated"
          active={state.status === "active"}
          variant="card"
          shape="swatch"
        />
      </div>

      {/* Fields grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Display name */}
        <FormInput
          label="Display Name"
          required
          value={state.displayName}
          onChange={(e) => updateField("displayName", e.target.value)}
          className="text-lg"
          placeholder="Nome do bot"
        />

        {/* Bot ID (read-only) */}
        <FormInput
          label="Bot ID"
          description="Identificador unico, nao editavel."
          value={botId}
          readOnly
          className="opacity-60 cursor-not-allowed"
        />

        {/* Status */}
        <FormSelect
          label="Status"
          value={state.status}
          onChange={(e) => updateField("status", e.target.value)}
          options={[
            { value: "active", label: "Active" },
            { value: "paused", label: "Paused" },
            { value: "archived", label: "Archived" },
          ]}
        />

        {/* Storage namespace (read-only) */}
        <FormInput
          label="Storage Namespace"
          description="Definido na criacao, nao editavel."
          value={state.storageNamespace}
          readOnly
          className="opacity-60 cursor-not-allowed"
        />
      </div>

      {/* Color picker */}
      <ColorPickerField
        label="Bot Color"
        hex={state.color}
        rgb={state.colorRgb}
        onHexChange={(hex) => updateField("color", hex)}
        onRgbChange={(rgb) => updateField("colorRgb", rgb)}
      />

      {/* Save */}
      <div className="flex items-center justify-end gap-3 pt-2 border-t border-[var(--border-subtle)]">
        {state.dirty.meta && (
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
          <span>{busyKey === "save" ? "Salvando..." : "Salvar identidade"}</span>
        </button>
      </div>
      </div>
    </LocalizedTree>
  );
}
