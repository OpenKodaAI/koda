"use client";

import { useMemo, useState } from "react";
import { Check, Clipboard, Eye, PencilLine, PanelRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface MarkdownEditorFieldProps {
  label: string;
  description?: string;
  value: string;
  onChange: (value: string) => void;
  minHeight?: string;
  placeholder?: string;
}

export function MarkdownEditorField({
  label,
  description,
  value,
  onChange,
  minHeight = "360px",
  placeholder,
}: MarkdownEditorFieldProps) {
  const [mode, setMode] = useState<"edit" | "preview" | "split">("edit");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const { tl } = useAppI18n();
  const characterCount = useMemo(() => value.length, [value]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setStatusMessage(tl("Markdown copiado"));
      window.setTimeout(() => setStatusMessage(null), 1600);
    } catch {
      setStatusMessage(tl("Nao foi possivel copiar"));
      window.setTimeout(() => setStatusMessage(null), 1600);
    }
  }

  async function handlePaste() {
    try {
      const clipboard = await navigator.clipboard.readText();
      if (!clipboard) return;
      onChange(clipboard);
      setStatusMessage(tl("Markdown colado do clipboard"));
      window.setTimeout(() => setStatusMessage(null), 1600);
    } catch {
      setStatusMessage(tl("Nao foi possivel colar"));
      window.setTimeout(() => setStatusMessage(null), 1600);
    }
  }

  const showEditor = mode === "edit" || mode === "split";
  const showPreview = mode === "preview" || mode === "split";
  const toolbarButtonClass =
    "inline-flex items-center gap-2 rounded-xl border border-[rgba(255,255,255,0.08)] bg-transparent px-3 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[rgba(255,255,255,0.14)] hover:bg-[rgba(255,255,255,0.02)] hover:text-[var(--text-primary)] shadow-none";
  const activeToolbarButtonClass =
    "border-[rgba(255,255,255,0.16)] bg-[rgba(255,255,255,0.05)] text-[var(--text-primary)]";

  return (
    <FormField label={label} description={description}>
      <div className="overflow-hidden rounded-[22px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.015)]">
        <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setMode("edit")}
              aria-pressed={mode === "edit"}
              className={`${toolbarButtonClass} ${mode === "edit" ? activeToolbarButtonClass : ""}`}
            >
              <PencilLine size={13} />
              {tl("Escrever")}
            </button>
            <button
              type="button"
              onClick={() => setMode("split")}
              aria-pressed={mode === "split"}
              className={`${toolbarButtonClass} ${mode === "split" ? activeToolbarButtonClass : ""}`}
            >
              <PanelRight size={13} />
              {tl("Lado a lado")}
            </button>
            <button
              type="button"
              onClick={() => setMode("preview")}
              aria-pressed={mode === "preview"}
              className={`${toolbarButtonClass} ${mode === "preview" ? activeToolbarButtonClass : ""}`}
            >
              <Eye size={13} />
              {tl("Preview")}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {statusMessage ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-[var(--text-tertiary)]">
                <Check size={12} />
                {statusMessage}
              </span>
            ) : null}
            <span className="tabular-nums text-[10px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {characterCount} {tl("caracteres")}
            </span>
            <button
              type="button"
              onClick={handlePaste}
              className={toolbarButtonClass}
            >
              <Clipboard size={13} />
              {tl("Colar")}
            </button>
            <button
              type="button"
              onClick={handleCopy}
              className={toolbarButtonClass}
            >
              <Clipboard size={13} />
              {tl("Copiar")}
            </button>
          </div>
        </div>

        <div className={`grid gap-0 ${mode === "split" ? "lg:grid-cols-2" : "grid-cols-1"}`}>
          {showEditor ? (
            <div className={showPreview ? "border-b border-[var(--border-subtle)] lg:border-b-0 lg:border-r" : ""}>
              <textarea
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className="w-full resize-y border-0 bg-transparent px-5 py-5 text-sm leading-7 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
                style={{ minHeight }}
                spellCheck
                placeholder={
                  placeholder
                    ? tl(placeholder)
                    : tl("Escreva em Markdown com instruções, critérios, exemplos e contexto útil para o agente.")
                }
              />
            </div>
          ) : null}

          {showPreview ? (
            <div
              className="session-richtext overflow-auto px-5 py-5"
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
          ) : null}
        </div>
      </div>
    </FormField>
  );
}
