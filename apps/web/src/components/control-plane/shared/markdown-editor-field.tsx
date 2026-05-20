"use client";

import { useId, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface MarkdownEditorFieldProps {
  label?: string;
  description?: string;
  value: string;
  onChange: (value: string) => void;
  minHeight?: string;
  placeholder?: string;
  hideFieldHeader?: boolean;
  textareaAriaLabel?: string;
  className?: string;
}

export function MarkdownEditorField({
  label,
  description,
  value,
  onChange,
  minHeight = "360px",
  placeholder,
  hideFieldHeader = false,
  textareaAriaLabel,
  className,
}: MarkdownEditorFieldProps) {
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const { t, tl } = useAppI18n();
  const editorId = useId();
  const characterCount = useMemo(() => value.length, [value]);

  const modeTabClass =
    "rounded-[5px] px-2.5 py-1 text-[11px] font-semibold leading-none text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]";
  const activeModeTabClass =
    "bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]";

  const editor = (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="relative rounded-[var(--radius-input)] border border-[color:var(--divider-hair)] bg-transparent transition-colors focus-within:border-[rgba(255,255,255,0.12)]">
        <div
          className="absolute right-2 top-2 z-10 inline-flex items-center gap-0.5 rounded-[6px] bg-[var(--panel-soft)] p-0.5 shadow-[0_1px_8px_rgba(0,0,0,0.16)]"
          role="tablist"
          aria-label={t("generated.controlPlane.modo_do_editor_markdown_d9321038")}
        >
          <button
            type="button"
            id={`${editorId}-preview-tab`}
            role="tab"
            onClick={() => setMode("preview")}
            aria-label={t("generated.controlPlane.preview_2f5eedc0")}
            aria-selected={mode === "preview"}
            aria-controls={`${editorId}-preview-panel`}
            className={cn(
              modeTabClass,
              mode === "preview" && activeModeTabClass,
            )}
          >
            {t("generated.controlPlane.preview_2f5eedc0")}
          </button>
          <button
            type="button"
            id={`${editorId}-markdown-tab`}
            role="tab"
            onClick={() => setMode("edit")}
            aria-label={t("generated.controlPlane.markdown_718e1b2b")}
            aria-selected={mode === "edit"}
            aria-controls={`${editorId}-markdown-panel`}
            className={cn(
              modeTabClass,
              mode === "edit" && activeModeTabClass,
            )}
          >
            {t("generated.controlPlane.markdown_718e1b2b")}
          </button>
        </div>

        {mode === "edit" ? (
          <textarea
            id={`${editorId}-markdown-panel`}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-label={textareaAriaLabel || label}
            className="block w-full resize-y rounded-[var(--radius-input)] bg-transparent px-3 pb-2.5 pt-11 text-[0.8125rem] leading-6 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
            style={{ minHeight }}
            spellCheck
            placeholder={
              placeholder
                ? tl(placeholder)
                : t("generated.controlPlane.escreva_em_markdown_com_instrucoes_criterios_05f27064")
            }
          />
        ) : (
          <div
            id={`${editorId}-preview-panel`}
            role="tabpanel"
            aria-labelledby={`${editorId}-preview-tab`}
            className="session-richtext overflow-auto rounded-[var(--radius-input)] px-3 pb-2.5 pt-11"
            style={{ minHeight }}
          >
            {value.trim() ? (
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {value}
              </ReactMarkdown>
            ) : (
              <p className="text-sm italic text-[var(--text-quaternary)]">
                {t("generated.controlPlane.nenhum_conteudo_para_visualizar_b4c7dc4c")}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex justify-end px-1">
        <span className="tabular-nums text-[10px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
          {characterCount} {t("generated.controlPlane.caracteres_e7774181")}
        </span>
      </div>
    </div>
  );

  if (hideFieldHeader) {
    return editor;
  }

  return (
    <FormField label={label || ""} description={description}>
      {editor}
    </FormField>
  );
}
