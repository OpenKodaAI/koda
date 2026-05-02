"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";

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
  const presence = useAnimatedPresence(open, null, { duration: 200 });
  const resolvedConfirmLabel =
    confirmLabel ?? t("controlPlane.shared.confirmation.confirm", { defaultValue: "Confirm" });

  useEffect(() => {
    if (!presence.isVisible) return;
    const timer = setTimeout(() => {
      cancelRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, [presence.isVisible]);

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onCancel);

  if (!presence.shouldRender) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        data-visible={presence.isVisible}
        onClick={onCancel}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] overflow-y-auto px-4 py-6 sm:px-6">
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-message"
          data-visible={presence.isVisible}
          className="app-modal-panel app-modal-anim relative w-full max-w-[26rem] p-5 sm:p-6"
          onClick={(event) => event.stopPropagation()}
        >
          <h2
            id="confirm-dialog-title"
            className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]"
          >
            {title}
          </h2>

          <p
            id="confirm-dialog-message"
            className="m-0 mt-2 text-[var(--font-size-sm)] leading-[1.55] text-[var(--text-tertiary)]"
          >
            {message}
          </p>

          <div className="mt-6 flex items-center justify-end gap-2">
            <button
              ref={cancelRef}
              type="button"
              onClick={onCancel}
              className="inline-flex h-9 items-center justify-center rounded-[var(--radius-panel-sm)] px-3.5 text-[var(--font-size-sm)] font-medium text-[var(--text-secondary)] transition-colors duration-[var(--transition-fast)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className="inline-flex h-9 items-center justify-center rounded-[var(--radius-panel-sm)] bg-[var(--tone-danger-bg-strong)] px-3.5 text-[var(--font-size-sm)] font-medium text-[var(--tone-danger-text)] transition-colors duration-[var(--transition-fast)] hover:bg-[color:var(--tone-danger-dot)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tone-danger-dot)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
            >
              {resolvedConfirmLabel}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
