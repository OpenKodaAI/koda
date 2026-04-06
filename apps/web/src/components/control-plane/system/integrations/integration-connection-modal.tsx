"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Lock, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";
import { renderIntegrationLogo } from "./integration-logos";
import type { GeneralSystemSettingsCredentialField } from "@/lib/control-plane";
import type { IntegrationCatalogEntry } from "./integration-catalog-data";

/* ------------------------------------------------------------------ */
/*  Connection modal                                                   */
/* ------------------------------------------------------------------ */

export function IntegrationConnectionModal({
  entry,
  onClose,
}: {
  entry: IntegrationCatalogEntry;
  onClose: () => void;
}) {
  const {
    integrationConnections,
    setCredentialField,
    connectIntegration,
    isIntegrationActionPending,
    integrationActionStatus,
  } = useSystemSettings();
  const { tl } = useAppI18n();

  const connection = integrationConnections[entry.key];
  const fields = (connection?.fields || []) as GeneralSystemSettingsCredentialField[];

  // Auto-focus first input in the modal
  useEffect(() => {
    if (!fields.length) return;
    const timer = setTimeout(() => {
      const el = document.querySelector<HTMLInputElement>(
        "[data-connection-modal] input",
      );
      el?.focus();
    }, 80);
    return () => clearTimeout(timer);
  }, [fields.length]);

  // Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  if (typeof document === "undefined" || !connection) return null;

  const logo = renderIntegrationLogo(entry.logoKey, "h-7 w-7");

  const handleConnect = async () => {
    await connectIntegration(entry.key);
    onClose();
  };

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel relative w-full max-w-lg overflow-hidden border-[var(--border-strong)]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="connection-modal-title"
          data-connection-modal
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          {/* Header */}
          <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${entry.gradientFrom}18` }}
              >
                {logo}
              </div>
              <div>
                <h3
                  id="connection-modal-title"
                  className="text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
                >
                  {tl("Conectar")} {entry.label}
                </h3>
                <p className="mt-0.5 text-sm text-[var(--text-quaternary)]">
                  {tl(entry.tagline)}
                </p>
              </div>
            </div>
          </div>

          {/* Credential fields */}
          <div className="space-y-3 px-6 py-5">
            {fields.map((field) => (
              <FieldShell
                key={field.key}
                label={field.label}
                description={
                  field.storage === "secret" && field.value_present
                    ? tl("Preencha apenas para substituir.")
                    : field.required
                      ? tl("Obrigatório")
                      : tl("Opcional")
                }
              >
                <div className="space-y-2">
                  {field.storage === "secret" && field.value_present ? (
                    <MaskedSecretPreview preview={field.preview} />
                  ) : null}
                  {field.storage === "secret" ? (
                    <SecretInput
                      value={field.value || ""}
                    onChange={(e) =>
                      setCredentialField(entry.key, field.key, (f) => ({
                        ...f,
                        value: e.target.value,
                          clear: false,
                        }))
                      }
                      placeholder={tl("Digite para substituir")}
                    />
                  ) : (
                    <input
                      className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                      type={field.input_type === "password" ? "password" : "text"}
                      value={field.value || ""}
                      onChange={(e) =>
                        setCredentialField(entry.key, field.key, (f) => ({
                          ...f,
                          value: e.target.value,
                          clear: false,
                        }))
                      }
                      placeholder={tl("Preencha o valor")}
                    />
                  )}
                </div>
                {field.storage === "secret" && field.value_present ? (
                  <button
                    type="button"
                    onClick={() =>
                      setCredentialField(entry.key, field.key, (f) => ({
                        ...f,
                        value: "",
                        clear: !f.clear,
                      }))
                    }
                    className={cn(
                      "mt-2 inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                      field.clear
                        ? "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]"
                        : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                    )}
                  >
                    <Trash2 size={12} />
                    {field.clear ? tl("Será removido ao salvar") : tl("Remover segredo")}
                  </button>
                ) : null}
              </FieldShell>
            ))}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-6 py-4">
            {/* Security indicator */}
            <div className="flex items-center gap-1.5 text-xs text-[var(--text-quaternary)]">
              <Lock size={11} />
              <span>{tl("Credenciais criptografadas")}</span>
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
                onClick={handleConnect}
                loading={isIntegrationActionPending(entry.key, "connect")}
                status={integrationActionStatus(entry.key, "connect")}
                loadingLabel={tl("Salvando")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-[var(--interactive-active-text)] transition-all"
                style={{
                  background: `linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))`,
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
