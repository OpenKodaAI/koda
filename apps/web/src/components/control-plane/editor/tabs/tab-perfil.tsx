"use client";

import { useMemo } from "react";
import { ShieldCheck } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { ColorPickerField } from "@/components/control-plane/shared/color-picker-field";
import { FormInput, FormSelect } from "@/components/control-plane/shared/form-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";

export function TabPerfil() {
  const { state, workspaces, updateField } = useBotEditor();
  const { tl } = useAppI18n();

  const botId = state.bot.id;
  const selectedWorkspace = useMemo(
    () => workspaces.items.find((item) => item.id === state.workspaceId) ?? null,
    [state.workspaceId, workspaces.items],
  );
  const workspaceOptions = useMemo(
    () => [
      { value: "", label: tl("Sem workspace") },
      ...workspaces.items.map((item) => ({ value: item.id, label: item.name })),
    ],
    [workspaces.items, tl],
  );
  const squadOptions = useMemo(() => {
    if (!selectedWorkspace) {
      return [{ value: "", label: tl("Sem squad") }];
    }
    return [
      { value: "", label: tl("Sem squad") },
      ...selectedWorkspace.squads.map((item) => ({ value: item.id, label: item.name })),
    ];
  }, [selectedWorkspace, tl]);

  function handleWorkspaceChange(nextWorkspaceId: string) {
    updateField("workspaceId", nextWorkspaceId);
    if (!nextWorkspaceId) {
      updateField("squadId", "");
      return;
    }
    const nextWorkspace = workspaces.items.find((item) => item.id === nextWorkspaceId);
    const squadStillValid = nextWorkspace?.squads.some((item) => item.id === state.squadId) ?? false;
    if (!squadStillValid) {
      updateField("squadId", "");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {tl("Identidade do Agente")}
          </h2>
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Nome, aparencia visual e enderecos do runtime publicados para este agente.")}
          </p>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex flex-col items-center gap-2 shrink-0">
            <BotAgentGlyph
              botId={botId}
              color={state.color || "#8B8B93"}
              className="h-[72px] w-[72px] rounded-[1.15rem] bot-swatch--animated"
              active={state.status === "active"}
              variant="card"
              shape="swatch"
            />
            <span className="text-[10px] text-[var(--text-quaternary)] font-mono">
              {botId}
            </span>
          </div>

          <div className="flex flex-col gap-4 flex-1 min-w-0">
            <FormInput
              label={tl("Nome do Agente")}
              required
              value={state.displayName}
              onChange={(event) => updateField("displayName", event.target.value)}
              placeholder={tl("Ex: Assistente de Vendas")}
            />
            <ColorPickerField
              label={tl("Cor do Agente")}
              hex={state.color}
              rgb={state.colorRgb}
              onHexChange={(hex) => updateField("color", hex)}
              onRgbChange={(rgb) => updateField("colorRgb", rgb)}
            />
          </div>
        </div>

        <SectionCollapsible title={tl("Configuracao de conexao")}>
          <div className="flex flex-col gap-4 pt-2">
            <p className="text-xs text-[var(--text-quaternary)]">
              {tl("Endpoints do runtime do agente. Altere apenas se estiver usando um runtime customizado.")}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormSelect
                label={tl("Workspace")}
                description={tl("Organizacao visual deste agente no catalogo.")}
                value={state.workspaceId}
                onChange={(event) => handleWorkspaceChange(event.target.value)}
                options={workspaceOptions}
              />
              <FormSelect
                label={tl("Squad")}
                description={tl("Time interno dentro do workspace selecionado.")}
                value={state.squadId}
                onChange={(event) => updateField("squadId", event.target.value)}
                options={squadOptions}
                disabled={!state.workspaceId}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormInput
                label={tl("URL do Runtime")}
                description={tl("Endereco base onde o agente esta hospedado.")}
                value={state.runtimeBaseUrl}
                onChange={(event) => updateField("runtimeBaseUrl", event.target.value)}
                placeholder="http://127.0.0.1:8080"
              />
              <FormInput
                label={tl("URL de Health Check")}
                description={tl("Endereco para verificar se o agente esta online.")}
                value={state.healthUrl}
                onChange={(event) => updateField("healthUrl", event.target.value)}
                placeholder="http://127.0.0.1:8080/health"
              />
            </div>
          </div>
        </SectionCollapsible>
      </section>

      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Escopo e credenciais")}
          description={tl("Variaveis compartilhadas, grants globais e segredos locais foram movidos para a aba Escopo para deixar a separacao de responsabilidades clara.")}
          icon={ShieldCheck}
        >
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Use a aba Escopo para conceder recursos globais, cadastrar segredos locais e controlar exatamente quais variaveis este agente pode receber do sistema.")}
          </p>
        </PolicyCard>
      </section>
    </div>
  );
}
