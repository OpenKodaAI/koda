"use client";

import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ScopeSystemPromptEditorProps {
  open: boolean;
  loading: boolean;
  saving: boolean;
  icon: ReactNode;
  title: string;
  subtitle: string;
  description: string;
  fieldLabel: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
}

export function ScopeSystemPromptEditor({
  open,
  loading,
  saving,
  icon,
  title,
  subtitle,
  description,
  fieldLabel,
  value,
  placeholder,
  onChange,
  onClose,
  onSave,
}: ScopeSystemPromptEditorProps) {
  const { tl } = useAppI18n();

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    open ? (
      <>
        <div
          className="app-overlay-backdrop z-[70]"
          onClick={onClose}
          aria-hidden="true"
        />
        <div className="app-modal-frame z-[80] items-center overflow-y-auto px-4 py-4 sm:px-6 sm:py-6">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="scope-system-prompt-editor-title"
              className="app-modal-panel relative flex h-[min(80vh,48rem)] w-full max-w-5xl flex-col overflow-hidden border-[var(--border-strong)]"
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

              <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14 sm:pr-16">
                <div className="flex items-start gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[0.75rem] border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.03)] text-[var(--text-secondary)]">
                    {icon}
                  </div>
                  <div className="min-w-0">
                    <h2
                      id="scope-system-prompt-editor-title"
                      className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]"
                    >
                      {title}
                    </h2>
                    <p className="mt-1 text-sm text-[var(--text-quaternary)]">
                      {description}
                    </p>
                    {!loading && subtitle ? (
                      <p className="mt-2 text-xs uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                        {subtitle}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-6 py-5">
                {loading ? (
                  <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-[var(--text-quaternary)]">
                    {tl("Carregando...")}
                  </div>
                ) : (
                  <div className="flex min-h-0 flex-1 flex-col">
                    <div className="min-h-0 flex-1">
                      <MarkdownEditorField
                        label={fieldLabel}
                        value={value}
                        onChange={onChange}
                        minHeight="min(46vh, 28rem)"
                        placeholder={placeholder}
                        hideFieldHeader
                        textareaAriaLabel={fieldLabel}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
                <button
                  type="button"
                  onClick={onClose}
                  className="button-shell button-shell--secondary"
                >
                  {tl("Cancelar")}
                </button>
                <button
                  type="button"
                  onClick={onSave}
                  disabled={loading || saving}
                  className="button-shell button-shell--primary"
                >
                  {saving ? tl("Salvando...") : tl("Salvar system prompt")}
                </button>
              </div>
            </div>
          </div>
      </>
      ) : null,
    document.body,
  );
}
