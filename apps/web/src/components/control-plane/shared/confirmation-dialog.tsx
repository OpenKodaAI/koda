"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ConfirmationDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmationDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps) {
  const { t } = useAppI18n();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const resolvedConfirmLabel =
    confirmLabel ?? t("controlPlane.shared.confirmation.confirm", { defaultValue: "Confirm" });

  // Focus trap: auto-focus cancel button when dialog opens
  useEffect(() => {
    if (open) {
      // Small delay so the element is rendered before focusing
      const timer = setTimeout(() => {
        cancelRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Escape to close
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [open]);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    open ? (
      <>
        <div
          className="app-overlay-backdrop z-[70]"
          onClick={onCancel}
          aria-hidden="true"
        />

        <div className="app-modal-frame z-[80] overflow-y-auto px-4 py-6 sm:px-6">
            <div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="confirm-dialog-title"
              aria-describedby="confirm-dialog-message"
              className="app-modal-panel relative w-full max-w-[34rem] p-5 sm:p-6"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mb-5 flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[0.75rem] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)]/80">
                    <AlertTriangle
                      size={18}
                      className="text-[var(--tone-warning-dot)]"
                    />
                  </div>

                  <div className="min-w-0 space-y-1">
                    <h2
                      id="confirm-dialog-title"
                      className="text-[1.1rem] font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
                    >
                      {title}
                    </h2>
                    <p className="text-sm text-[rgba(255,255,255,0.46)]">
                      {t("controlPlane.shared.confirmation.confirm", { defaultValue: "Confirm action" })}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={onCancel}
                  className="button-shell button-shell--secondary button-shell--icon h-10 w-10 shrink-0 text-[var(--text-secondary)]"
                  aria-label={t("common.close")}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-5">
                <p
                  id="confirm-dialog-message"
                  className="max-w-[42ch] text-[0.98rem] leading-8 text-[var(--text-secondary)]"
                >
                  {message}
                </p>

                <div className="flex flex-wrap items-center justify-end gap-3 border-t border-[rgba(255,255,255,0.07)] pt-5">
                  <button
                    ref={cancelRef}
                    type="button"
                    onClick={onCancel}
                    className="button-shell button-shell--secondary min-w-[8rem]"
                  >
                    <span>{t("common.cancel")}</span>
                  </button>
                  <button
                    type="button"
                    onClick={onConfirm}
                    className="button-shell min-w-[8rem]"
                    style={{
                      borderColor: "var(--tone-danger-border)",
                      background: "rgba(196, 48, 52, 0.14)",
                      color: "var(--tone-danger-text)",
                      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
                    }}
                  >
                    <span>{resolvedConfirmLabel}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
      </>
      ) : null,
    document.body
  );
}
