"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Lock, Trash2, X } from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import type { AgentIntegrationEntry } from "@/hooks/use-agent-integration-permissions";

type EditableField = {
  key: string;
  label: string;
  storage: string;
  required?: boolean;
  input_type?: string;
  value: string;
  value_present?: boolean;
  preview?: string;
  clear?: boolean;
};

type CoreConnectionModalProps = {
  entry: AgentIntegrationEntry;
  onClose: () => void;
  onSave: (payload: {
    auth_method: string;
    source_origin: string;
    allow_local_session: boolean;
    fields: Array<{ key: string; value: string; clear?: boolean }>;
  }) => Promise<void>;
};

function formatAuthModeLabel(value: string, tl: (text: string, vars?: Record<string, string | number>) => string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "local_session") return tl("Sessão local");
  if (normalized === "assume_role") return tl("Assume role");
  if (normalized === "access_key") return tl("Access key");
  if (normalized === "service_account") return tl("Service account");
  if (normalized === "service_account_key") return tl("Chave de service account");
  if (normalized === "oauth_user") return tl("OAuth do usuário");
  if (normalized === "oauth_confidential") return tl("OAuth confidencial");
  return value.replace(/_/g, " ");
}

export function CoreConnectionModal({
  entry,
  onClose,
  onSave,
}: CoreConnectionModalProps) {
  const { tl } = useAppI18n();
  const connection = entry.coreConnection ?? null;
  const authModes = entry.coreIntegration?.auth_modes ?? [];
  const [authMethod, setAuthMethod] = useState(
    connection?.auth_method ?? entry.coreIntegration?.auth_mode ?? authModes[0] ?? "manual",
  );
  const [allowLocalSession, setAllowLocalSession] = useState(
    Boolean(connection?.metadata?.allow_local_session),
  );
  const [fields, setFields] = useState<EditableField[]>(() =>
    ((connection?.fields ?? []) as Array<Record<string, unknown>>).map((field) => ({
      key: String(field.key ?? ""),
      label: String(field.label ?? field.key ?? ""),
      storage: String(field.storage ?? "env"),
      required: Boolean(field.required),
      input_type: typeof field.input_type === "string" ? field.input_type : undefined,
      value: typeof field.value === "string" ? field.value : "",
      value_present: Boolean(field.value_present),
      preview: typeof field.preview === "string" ? field.preview : "",
      clear: false,
    })),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const el = document.querySelector<HTMLInputElement>("[data-core-connection-modal] input");
      el?.focus();
    }, 80);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const canSave = useMemo(
    () => !(authMethod === "local_session" && !allowLocalSession),
    [allowLocalSession, authMethod],
  );

  if (typeof document === "undefined") return null;

  const logo = renderIntegrationLogo(entry.logoKey, "h-7 w-7");

  const updateField = (key: string, patch: Partial<EditableField>) => {
    setFields((current) =>
      current.map((field) => (field.key === key ? { ...field, ...patch } : field)),
    );
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      await onSave({
        auth_method: authMethod,
        source_origin: authMethod === "local_session" ? "local_session" : "agent_binding",
        allow_local_session: authMethod === "local_session" ? allowLocalSession : false,
        fields: fields.map((field) => ({
          key: field.key,
          value: field.value,
          clear: Boolean(field.clear),
        })),
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <>
      <div className="app-overlay-backdrop z-[70]" onClick={onClose} aria-hidden="true" />

      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel relative w-full max-w-lg overflow-hidden border-[var(--border-strong)]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="core-connection-modal-title"
          data-core-connection-modal
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${entry.accentFrom}18` }}
              >
                {logo}
              </div>
              <div>
                <h3
                  id="core-connection-modal-title"
                  className="text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
                >
                  {tl("Conectar")} {entry.label}
                </h3>
                <p className="mt-0.5 text-sm text-[var(--text-quaternary)]">
                  {tl("Esse binding fica isolado neste agente e nunca herda auth implícita da máquina.")}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4 px-6 py-5">
            {authModes.length > 0 ? (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  {tl("Modo de autenticação")}
                </span>
                <select
                  value={authMethod}
                  onChange={(event) => setAuthMethod(event.target.value)}
                  className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                >
                  {authModes.map((mode) => (
                    <option key={mode} value={mode}>
                      {formatAuthModeLabel(mode, tl)}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {authMethod === "local_session" ? (
              <div className="rounded-xl border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-4 py-3 text-sm text-[var(--tone-warning-text)]">
                <p>{tl("A sessão local usa a autenticação desta máquina e não é portátil entre agentes.")}</p>
                <label className="mt-3 flex items-start gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={allowLocalSession}
                    onChange={(event) => setAllowLocalSession(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>{tl("Confirmo que quero permitir explicitamente o uso da sessão local neste agente.")}</span>
                </label>
              </div>
            ) : null}

            {fields.map((field) => (
              <label key={field.key} className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  {field.label}
                </span>
                <span className="text-[11px] text-[var(--text-quaternary)]">
                  {field.storage === "secret" && field.value_present
                    ? tl("Preencha apenas para substituir.")
                    : field.required
                      ? tl("Obrigatório")
                      : tl("Opcional")}
                </span>
                {field.storage === "secret" && field.value_present ? (
                  <MaskedSecretPreview preview={field.preview} />
                ) : null}
                {field.storage === "secret" ? (
                  <SecretInput
                    value={field.value}
                    onChange={(event) =>
                      updateField(field.key, {
                        value: event.target.value,
                        clear: false,
                      })
                    }
                    placeholder={tl("Digite para substituir")}
                  />
                ) : (
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type={field.input_type === "password" ? "password" : "text"}
                    value={field.value}
                    onChange={(event) =>
                      updateField(field.key, {
                        value: event.target.value,
                        clear: false,
                      })
                    }
                    placeholder={tl("Preencha o valor")}
                  />
                )}
                {field.storage === "secret" && field.value_present ? (
                  <button
                    type="button"
                    onClick={() =>
                      updateField(field.key, {
                        value: "",
                        clear: !field.clear,
                      })
                    }
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                      field.clear
                        ? "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]"
                        : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                    )}
                  >
                    <Trash2 size={12} />
                    {field.clear ? tl("Será removido ao salvar") : tl("Remover segredo")}
                  </button>
                ) : null}
              </label>
            ))}
          </div>

          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-6 py-4">
            <div className="flex items-center gap-1.5 text-xs text-[var(--text-quaternary)]">
              <Lock size={11} />
              <span>{tl("Binding por agente com segredos criptografados")}</span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                {tl("Cancelar")}
              </button>
              <AsyncActionButton
                type="button"
                onClick={handleSave}
                loading={saving}
                disabled={!canSave}
                loadingLabel={tl("Salvando")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-[var(--interactive-active-text)] transition-all"
                style={{
                  background:
                    "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                  border: "1px solid var(--interactive-active-border)",
                }}
              >
                {tl("Salvar conexão")}
              </AsyncActionButton>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
