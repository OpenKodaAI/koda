"use client";

import { useMemo, useState } from "react";
import { Eye, PencilLine } from "lucide-react";
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
  const { tl } = useAppI18n();
  const characterCount = useMemo(() => value.length, [value]);

  const toolbarButtonClass =
    "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]";
  const activeToolbarButtonClass = "text-[var(--text-primary)]";

  const editor = (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setMode("edit")}
            aria-pressed={mode === "edit"}
            className={cn(
              toolbarButtonClass,
              mode === "edit" && activeToolbarButtonClass,
            )}
          >
            <PencilLine size={12} strokeWidth={1.75} />
            {tl("Editar")}
          </button>
          <button
            type="button"
            onClick={() => setMode("preview")}
            aria-pressed={mode === "preview"}
            className={cn(
              toolbarButtonClass,
              mode === "preview" && activeToolbarButtonClass,
            )}
          >
            <Eye size={12} strokeWidth={1.75} />
            {tl("Preview")}
          </button>
        </div>

        <span className="tabular-nums text-[10px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
          {characterCount} {tl("caracteres")}
        </span>
      </div>

      {mode === "edit" ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={textareaAriaLabel || label}
          className="w-full resize-y rounded-[var(--radius-input)] border border-[color:var(--divider-hair)] bg-transparent px-3 py-2.5 text-[0.8125rem] leading-6 text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-quaternary)] focus:border-[rgba(255,255,255,0.12)]"
          style={{ minHeight }}
          spellCheck
          placeholder={
            placeholder
              ? tl(placeholder)
              : tl("Escreva em Markdown com instruções, critérios, exemplos e contexto útil para o agente.")
          }
        />
      ) : (
        <div
          className="session-richtext overflow-auto rounded-[var(--radius-input)] border border-[color:var(--divider-hair)] px-3 py-2.5"
          style={{ minHeight }}
        >
          {value.trim() ? (
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
              {value}
            </ReactMarkdown>
          ) : (
            <p className="text-sm italic text-[var(--text-quaternary)]">
              {tl("Nenhum conteudo para visualizar")}
            </p>
          )}
        </div>
      )}
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
