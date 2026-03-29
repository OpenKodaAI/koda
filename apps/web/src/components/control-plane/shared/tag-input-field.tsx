"use client";

import { useState, useCallback, type KeyboardEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ClipboardPaste, X } from "lucide-react";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface TagInputFieldProps {
  label: string;
  description?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  maxTags?: number;
}

export function TagInputField({
  label,
  description,
  values,
  onChange,
  placeholder = "Digite e pressione Enter...",
  maxTags,
}: TagInputFieldProps) {
  const { tl } = useAppI18n();
  const [input, setInput] = useState("");

  const addTag = useCallback(
    (raw: string) => {
      const tag = raw.trim();
      if (!tag) return;
      if (values.includes(tag)) return;
      if (maxTags && values.length >= maxTags) return;
      onChange([...values, tag]);
      setInput("");
    },
    [values, onChange, maxTags],
  );

  const removeTag = useCallback(
    (index: number) => {
      onChange(values.filter((_, i) => i !== index));
    },
    [values, onChange],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addTag(input);
      } else if (e.key === "Backspace" && !input && values.length > 0) {
        removeTag(values.length - 1);
      }
    },
    [input, values, addTag, removeTag],
  );

  const isFull = maxTags !== undefined && values.length >= maxTags;

  async function handlePaste() {
    try {
      const clipboard = await navigator.clipboard.readText();
      if (!clipboard) return;
      clipboard
        .split(/\n|,/g)
        .map((entry) => entry.trim())
        .filter(Boolean)
        .forEach((entry) => addTag(entry));
    } catch {
      // Ignore clipboard failures and allow manual entry.
    }
  }

  return (
    <FormField label={label} description={description}>
      <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-4 shadow-[0_12px_32px_rgba(0,0,0,0.06)]">
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
            {tl("Etiquetas curtas")}
          </span>
          <button
            type="button"
            onClick={handlePaste}
            className="button-pill text-xs"
            disabled={isFull}
          >
            <ClipboardPaste size={13} />
            {tl("Colar")}
          </button>
        </div>

        <div
          className="field-shell flex min-h-[56px] flex-wrap items-center gap-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-3 cursor-text"
          onClick={(event) => {
            const inputElement = (event.currentTarget as HTMLElement).querySelector("input");
            inputElement?.focus();
          }}
        >
          <AnimatePresence>
            {values.map((tag, index) => (
              <motion.span
                key={tag}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-tint-strong)] pl-3 pr-1.5 py-1 text-xs text-[var(--text-secondary)]"
              >
                {tag}
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    removeTag(index);
                  }}
                  className="rounded-full p-1 transition-colors hover:bg-[var(--surface-hover-strong)] hover:text-[var(--tone-danger-text)]"
                  aria-label={`${tl("Remover")} ${tag}`}
                >
                  <X size={10} />
                </button>
              </motion.span>
            ))}
          </AnimatePresence>

          {!isFull ? (
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              className="min-w-[180px] flex-1 bg-transparent border-none outline-none text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
              placeholder={values.length === 0 ? tl(placeholder) : tl("Digite e pressione Enter")}
            />
          ) : null}
        </div>

        <span className="mt-3 block text-[11px] text-[var(--text-quaternary)]">
          {isFull
            ? tl("Limite de {{count}} itens atingido", { count: maxTags ?? 0 })
            : tl("Pressione Enter para adicionar ou cole varios itens separados por virgula ou linha")}
          {values.length > 0 && !isFull
            ? ` · ${values.length} ${tl(values.length !== 1 ? "itens" : "item")}`
            : ""}
        </span>
      </div>
    </FormField>
  );
}
