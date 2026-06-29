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
  const { t } = useAppI18n();

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
            label={t("generated.controlPlane.nome_do_agente_04e75caf")}
            required
            value={state.displayName}
            onChange={(event) => updateField("displayName", event.target.value)}
            placeholder={t("generated.controlPlane.ex_assistente_de_vendas_c23de2f4")}
          />
          <FormInput
            label={t("generated.controlPlane.missao_38786ee2")}
            description={t("generated.controlPlane.uma_frase_curta_sobre_o_que_o_agente_faz_apa_888d69c2")}
            value={missionProfile.mission}
            onChange={(event) => updateMission(event.target.value)}
            placeholder={t("generated.controlPlane.ex_resolver_tickets_com_grounding_816f3a4e")}
          />
          <ColorPickerField
            label={t("generated.controlPlane.cor_a63c4fed")}
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
            {t("generated.controlPlane.canais_de_comunicacao_9f375cf8")}
          </h2>
          <p className="text-sm text-[var(--text-tertiary)]">
            {t("generated.controlPlane.conecte_canais_de_entrada_para_que_usuarios__7ab51769")}
          </p>
        </div>
        <ChannelConnectionArea />
      </section>
    </div>
  );
}
