"use client";

import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { ColorPickerField } from "@/components/control-plane/shared/color-picker-field";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { ChannelConnectionArea } from "@/components/control-plane/editor/channel-connection-area";

export function TabPerfil() {
  const { state, updateField } = useBotEditor();
  const { tl } = useAppI18n();

  const botId = state.bot.id;

  return (
    <div className="flex flex-col gap-8">
      {/* Identity — compact horizontal layout */}
      <section className="flex items-start gap-5">
        {/* Avatar */}
        <div className="flex flex-col items-center gap-1.5 shrink-0 pt-1">
          <BotAgentGlyph
            botId={botId}
            color={state.color || "#8B8B93"}
            className="h-14 w-14 rounded-[0.9rem] bot-swatch--animated"
            active={state.status === "active"}
            variant="card"
            shape="swatch"
          />
          <span className="text-[9px] text-[var(--text-quaternary)] font-mono">
            {botId}
          </span>
        </div>

        {/* Name + Color inline */}
        <div className="flex flex-col gap-3 flex-1 min-w-0">
          <FormInput
            label={tl("Nome do Agente")}
            required
            value={state.displayName}
            onChange={(event) => updateField("displayName", event.target.value)}
            placeholder={tl("Ex: Assistente de Vendas")}
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

      {/* Channels */}
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
