"use client";

import { useMemo } from "react";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import { ColorPickerField } from "@/components/control-plane/shared/color-picker-field";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { ChannelConnectionArea } from "@/components/control-plane/editor/channel-connection-area";
import {
  parseMissionProfile,
  serializeMissionProfile,
} from "@/lib/policy-serializers";

export function TabPerfil() {
  const { state, updateField, updateAgentSpecField } = useAgentEditor();
  const { tl } = useAppI18n();

  const agentId = state.agent.id;

  const missionProfile = useMemo(
    () => parseMissionProfile(state.missionProfileJson),
    [state.missionProfileJson],
  );

  function updateMission(nextMission: string) {
    updateAgentSpecField(
      "missionProfileJson",
      serializeMissionProfile({ ...missionProfile, mission: nextMission }),
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex items-start gap-5">
        <div className="flex flex-col items-center gap-1.5 shrink-0 pt-1">
          <AgentSigil
            agentId={agentId}
            label={state.displayName || agentId}
            color={state.color || "#8B8B93"}
            status={state.status}
            size="lg"
          />
          <span className="text-[9px] text-[var(--text-quaternary)] font-mono">
            {agentId}
          </span>
        </div>

        <div className="flex flex-col gap-3 flex-1 min-w-0">
          <FormInput
            label={tl("Nome do Agente")}
            required
            value={state.displayName}
            onChange={(event) => updateField("displayName", event.target.value)}
            placeholder={tl("Ex: Assistente de Vendas")}
          />
          <FormInput
            label={tl("Missao")}
            description={tl("Uma frase curta sobre o que o agente faz. Aparece no prompt e no catalogo.")}
            value={missionProfile.mission}
            onChange={(event) => updateMission(event.target.value)}
            placeholder={tl("Ex: Resolver tickets com grounding")}
          />
          <ColorPickerField
            label={tl("Cor")}
            hex={state.color}
            rgb={state.colorRgb}
            onHexChange={(hex) => updateField("color", hex)}
            onRgbChange={(rgb) => updateField("colorRgb", rgb)}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {tl("Canais de comunicacao")}
          </h2>
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Conecte canais de entrada para que usuarios possam interagir com este agente.")}
          </p>
        </div>
        <ChannelConnectionArea />
      </section>
    </div>
  );
}
