"use client";

import { Plus, Pencil, Trash2 } from "lucide-react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { MetaTag } from "@/components/control-plane/system/shared/meta-tag";
import { MaskedSecretPreview } from "@/components/ui/secret-controls";
import { removeVariable } from "@/lib/system-settings-model";

export function SectionVariables() {
  const { draft, setField, openNewVariable, openEditVariable } = useSystemSettings();
  const { tl } = useAppI18n();
  const variables = draft.values.variables;

  return (
    <SettingsSectionShell
      sectionId="variables"
      title="settings.sections.variables.label"
      description="settings.sections.variables.description"
    >
      <SettingsFieldGroup title={tl("Variables")}>
        <div className="flex flex-col gap-4 py-1">
          <div className="flex flex-wrap items-start justify-between gap-3 px-1">
            <div>
              <p className="text-xs leading-relaxed text-[var(--text-quaternary)]">
                {tl("Operator-defined resources with explicit type, description and scope.")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <MetaTag label={tl("{{count}} item(ns)", { count: variables.length })} />
              <button
                type="button"
                onClick={openNewVariable}
                className="inline-flex items-center gap-2 rounded-lg bg-[rgba(113,219,190,0.18)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[rgba(113,219,190,0.24)]"
              >
                <Plus size={14} />
                {tl("Adicionar")}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {variables.map((variable) => (
              <div
                key={variable.key}
                className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.015)] px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="break-all font-mono text-sm font-medium text-[var(--text-primary)]">
                      {variable.key}
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-quaternary)]">
                      {variable.description || tl("Sem descrição")}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <MetaTag label={variable.type === "secret" ? tl("Segredo") : tl("Texto")} />
                    <MetaTag
                      label={
                        variable.scope === "bot_grant"
                          ? tl("Disponível por grant")
                          : tl("Somente sistema")
                      }
                      tone={variable.scope === "bot_grant" ? "accent" : "neutral"}
                    />
                    <button
                      type="button"
                      onClick={() => openEditVariable(variable)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                    >
                      <Pencil size={13} />
                      {tl("Editar")}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setField("variables", removeVariable(variables, variable.key))
                      }
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[rgba(255,110,110,0.18)] px-3 py-1.5 text-xs text-[var(--tone-danger-text)] transition-colors hover:bg-[rgba(255,110,110,0.08)]"
                    >
                      <Trash2 size={13} />
                      {tl("Remover")}
                    </button>
                  </div>
                </div>
                <div className="mt-3">
                  {variable.type === "secret" ? (
                    <MaskedSecretPreview preview={variable.preview} />
                  ) : (
                    <div className="rounded-lg bg-[rgba(255,255,255,0.025)] px-3 py-2 font-mono text-xs break-all text-[var(--text-secondary)]">
                      {variable.value || tl("Sem valor preenchido")}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {variables.length === 0 && (
              <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--panel-muted)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
                {tl("Nenhuma variável global customizada foi adicionada ainda.")}
              </div>
            )}
          </div>
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
