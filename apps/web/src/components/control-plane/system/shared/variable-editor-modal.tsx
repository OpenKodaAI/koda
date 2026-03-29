"use client";

import { createPortal } from "react-dom";
import { Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GeneralSystemSettingsVariable } from "@/lib/control-plane";
import { FieldShell } from "./field-shell";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function VariableEditorModal({
  draft,
  onChange,
  onCancel,
  onConfirm,
}: {
  draft: GeneralSystemSettingsVariable;
  onChange: (next: GeneralSystemSettingsVariable) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { tl } = useAppI18n();
  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel relative w-full max-w-2xl overflow-hidden border-[var(--border-strong)]"
          onClick={(event) => event.stopPropagation()}
        >
        <button
          type="button"
          onClick={onCancel}
          className="app-surface-close"
          aria-label={tl("Fechar modal")}
        >
          <X className="h-4 w-4" />
        </button>

        <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14 sm:pr-16">
          <div>
            <h3 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {draft.key ? tl("Editar variável") : tl("Nova variável")}
            </h3>
            <p className="mt-1 text-sm text-[var(--text-quaternary)]">
              {tl("Defina o tipo, escopo e descrição do recurso global.")}
            </p>
          </div>
        </div>

        <div className="grid gap-3 px-6 py-5 md:grid-cols-2">
          <FieldShell label={tl("Nome")} description={tl("Use um nome em formato de variável de ambiente.")}>
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.key}
              onChange={(event) => onChange({ ...draft, key: event.target.value })}
              placeholder="TEAM_NAME"
            />
          </FieldShell>

          <FieldShell label={tl("Tipo")} description={tl("Segredos ficam criptografados e mascarados em leitura.")}>
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.type}
              onChange={(event) =>
                onChange({
                  ...draft,
                  type: event.target.value === "secret" ? "secret" : "text",
                  clear: false,
                })
              }
            >
              <option value="text">{tl("Texto")}</option>
              <option value="secret">{tl("Segredo")}</option>
            </select>
          </FieldShell>

          <FieldShell label={tl("Escopo")} description={tl("Controle se o valor pode ser concedido explicitamente a bots.")}>
            <select
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.scope}
              onChange={(event) =>
                onChange({
                  ...draft,
                  scope: event.target.value === "bot_grant" ? "bot_grant" : "system_only",
                })
              }
            >
              <option value="system_only">{tl("Somente sistema")}</option>
              <option value="bot_grant">{tl("Disponível para bots mediante grant")}</option>
            </select>
          </FieldShell>

          <FieldShell label={tl("Descrição")} description={tl("Contexto curto para o operador lembrar o propósito.")}>
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={draft.description}
              onChange={(event) => onChange({ ...draft, description: event.target.value })}
              placeholder={tl("Fila operacional do time")}
            />
          </FieldShell>

          <div className="md:col-span-2">
            <FieldShell
              label={draft.type === "secret" ? tl("Valor do segredo") : tl("Valor")}
              description={
                draft.type === "secret" && draft.value_present
                  ? `${tl("Valor atual mascarado")}: ${draft.preview || tl("já configurado")}`
                  : tl("O valor será salvo globalmente no control plane.")
              }
            >
              <div className="space-y-3">
                {draft.type === "secret" && draft.value_present ? (
                  <MaskedSecretPreview preview={draft.preview} />
                ) : null}
                {draft.type === "secret" ? (
                  <SecretInput
                    value={draft.value}
                    onChange={(event) => onChange({ ...draft, value: event.target.value, clear: false })}
                    placeholder={tl("Digite apenas se quiser substituir")}
                  />
                ) : (
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    value={draft.value}
                    onChange={(event) => onChange({ ...draft, value: event.target.value, clear: false })}
                    placeholder={tl("valor")}
                  />
                )}
              </div>
              {draft.type === "secret" && draft.value_present ? (
                <button
                  type="button"
                  onClick={() => onChange({ ...draft, value: "", clear: !draft.clear })}
                  className={cn(
                    "mt-3 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                    draft.clear
                      ? "border-[rgba(255,110,110,0.3)] bg-[rgba(255,110,110,0.12)] text-[var(--tone-danger-text)]"
                      : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                  )}
                >
                  <Trash2 size={14} />
                  {draft.clear ? tl("Segredo será removido ao salvar") : tl("Marcar para remover")}
                </button>
              ) : null}
            </FieldShell>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            {tl("Cancelar")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-[rgba(113,219,190,0.18)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[rgba(113,219,190,0.24)]"
          >
            {tl("Aplicar")}
          </button>
        </div>
      </div>
      </div>
    </>,
    document.body
  );
}
