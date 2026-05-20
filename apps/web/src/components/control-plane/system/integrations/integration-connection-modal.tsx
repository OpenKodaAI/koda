"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Lock, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { SecretInput } from "@/components/ui/secret-controls";
import { renderIntegrationLogo } from "./integration-logos";
import type { GeneralSystemSettingsCredentialField } from "@/lib/control-plane";
import type { IntegrationCatalogEntry } from "./integration-catalog-data";

/*  Connection modal                                                   */

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
  const { t, tl } = useAppI18n();

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
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel app-modal-anim relative w-full max-w-lg overflow-hidden border-[var(--border-strong)]"
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
            aria-label={t("generated.controlPlane.fechar_modal_1b5b2901")}
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
                  {t("generated.controlPlane.conectar_a587e076")} {entry.label}
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
                    ? t("generated.controlPlane.preencha_apenas_para_substituir_f0486ea6")
                    : field.required
                      ? t("generated.controlPlane.obrigatorio_ea9fd1bf")
                      : t("generated.controlPlane.opcional_f6c7765c")
                }
              >
                <div className="space-y-2">
                  {field.storage === "secret" && field.value_present ? (
                    <span className="inline-flex items-center gap-1 self-start rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                      {t("generated.controlPlane.configurada_df5188a8")}
                    </span>
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
                      placeholder={t("generated.controlPlane.digite_para_substituir_5f794493")}
                    />
                  ) : (
                    <input
                      className="field-shell text-[var(--text-primary)]"
                      type={field.input_type === "password" ? "password" : "text"}
                      value={field.value || ""}
                      onChange={(e) =>
                        setCredentialField(entry.key, field.key, (f) => ({
                          ...f,
                          value: e.target.value,
                          clear: false,
                        }))
                      }
                      placeholder={t("generated.controlPlane.preencha_o_valor_b94f6d3d")}
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
                    {field.clear ? t("generated.controlPlane.sera_removido_ao_salvar_8111eef5") : t("generated.controlPlane.remover_segredo_a2cb1ebd")}
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
              <span>{t("generated.controlPlane.credenciais_criptografadas_657054e7")}</span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                {t("generated.controlPlane.cancelar_091200fb")}
              </button>
              <AsyncActionButton
                type="button"
                onClick={handleConnect}
                loading={isIntegrationActionPending(entry.key, "connect")}
                status={integrationActionStatus(entry.key, "connect")}
                loadingLabel={t("generated.controlPlane.salvando_7eeded02")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-[var(--interactive-active-text)] transition-all"
                style={{
                  background: `linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))`,
                  border: "1px solid var(--interactive-active-border)",
                }}
              >
                {t("generated.controlPlane.salvar_conexao_53e83802")}
              </AsyncActionButton>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
