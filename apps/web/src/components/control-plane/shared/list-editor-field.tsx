"use client";

import { useCallback, useMemo, useState } from "react";
import { AnimatePresence, Reorder } from "framer-motion";
import { ClipboardPaste, GripVertical, Plus, Trash2 } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FormField } from "./form-field";

interface ListEditorFieldProps {
  label: string;
  description?: string;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
  maxItems?: number;
}

interface ListItem {
  id: string;
  text: string;
}

export function ListEditorField({
  label,
  description,
  items,
  onChange,
  placeholder = "Novo item...",
  maxItems,
}: ListEditorFieldProps) {
  const { tl } = useAppI18n();
  const [newItem, setNewItem] = useState("");
  const wrappedItems = useMemo(() => {
    return items.map((text, index) => ({
      id: `${index}-${text}`,
      text,
    }));
  }, [items]);

  const handleReorder = useCallback(
    (newOrder: ListItem[]) => {
      onChange(newOrder.map((item) => item.text));
    },
    [onChange],
  );

  const commitItems = useCallback(
    (raw: string) => {
      const nextEntries = raw
        .split(/\n|,/g)
        .map((entry) => entry.trim())
        .filter(Boolean);
      if (nextEntries.length === 0) return;

      const uniqueItems = [...items];
      for (const entry of nextEntries) {
        if (uniqueItems.includes(entry)) continue;
        if (maxItems && uniqueItems.length >= maxItems) break;
        uniqueItems.push(entry);
      }

      onChange(uniqueItems);
      setNewItem("");
    },
    [items, maxItems, onChange],
  );

  const addItem = useCallback(() => {
    commitItems(newItem);
  }, [commitItems, newItem]);

  const removeItem = useCallback(
    (id: string) => {
      const filtered = wrappedItems.filter((item) => item.id !== id);
      onChange(filtered.map((item) => item.text));
    },
    [onChange, wrappedItems],
  );

  const updateItem = useCallback(
    (id: string, value: string) => {
      const updated = wrappedItems.map((item) =>
        item.id === id ? { ...item, text: value } : item,
      );
      onChange(updated.map((item) => item.text));
    },
    [onChange, wrappedItems],
  );

  async function handlePaste() {
    try {
      const clipboard = await navigator.clipboard.readText();
      if (!clipboard) return;
      commitItems(clipboard);
    } catch {
      // Ignore clipboard read failures; direct paste into the textarea remains available.
    }
  }

  return (
    <FormField label={label} description={description}>
      <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-4 shadow-[0_12px_40px_rgba(0,0,0,0.08)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
            {tl("Uma politica por linha")}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePaste}
              className="button-pill text-xs"
            >
              <ClipboardPaste size={13} />
              {tl("Colar lista")}
            </button>
            <span className="text-[11px] text-[var(--text-quaternary)]">
              {items.length} {tl(items.length === 1 ? "item" : "itens")}
            </span>
          </div>
        </div>

        {wrappedItems.length > 0 ? (
          <Reorder.Group
            axis="y"
            values={wrappedItems}
            onReorder={handleReorder}
            className="flex flex-col gap-2"
          >
            <AnimatePresence>
              {wrappedItems.map((item, index) => (
                <Reorder.Item
                  key={item.id}
                  value={item}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <div className="group flex items-start gap-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-3">
                    <span className="mt-2 cursor-grab text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-tertiary)] touch-none">
                      <GripVertical size={14} />
                    </span>

                    <span className="min-w-[1.4rem] pt-2 text-right text-[11px] tabular-nums text-[var(--text-quaternary)]">
                      {index + 1}.
                    </span>

                    <textarea
                      value={item.text}
                      onChange={(event) => updateItem(item.id, event.target.value)}
                      rows={2}
                      className="field-shell min-h-[72px] flex-1 resize-y rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-3 text-sm leading-6 text-[var(--text-primary)]"
                      spellCheck
                    />

                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      className="mt-1 p-2 text-[var(--text-quaternary)] opacity-0 transition-colors group-hover:opacity-100 hover:text-[var(--tone-danger-text)]"
                      aria-label={tl("Remover item {{index}}", { index: index + 1 })}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </Reorder.Item>
              ))}
            </AnimatePresence>
          </Reorder.Group>
        ) : null}

        <div className="mt-4 rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
              {tl("Adicionar novas entradas")}
            </span>
            <span className="text-[11px] text-[var(--text-quaternary)]">
              {tl("Cole varias linhas ou escreva uma por vez")}
            </span>
          </div>

          <textarea
            value={newItem}
            onChange={(event) => setNewItem(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                addItem();
              }
            }}
            rows={4}
            className="field-shell w-full resize-y rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-4 text-sm leading-6 text-[var(--text-primary)]"
            placeholder={
              maxItems && items.length >= maxItems
                ? tl("Maximo de {{maxItems}} itens", { maxItems })
                : `${tl(placeholder)}\n${tl("Dica: use uma linha por item para adicionar varios de uma vez.")}`
            }
            disabled={maxItems !== undefined && items.length >= maxItems}
            spellCheck
          />

          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-[11px] text-[var(--text-quaternary)]">
              {tl("Use Ctrl/Cmd + Enter para adicionar rapidamente")}
            </span>
            <button
              type="button"
              onClick={addItem}
              disabled={
                !newItem.trim() ||
                (maxItems !== undefined && items.length >= maxItems)
              }
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] disabled:opacity-30"
              aria-label={tl("Adicionar item")}
            >
              <Plus size={14} />
              {tl("Adicionar")}
            </button>
          </div>
        </div>
      </div>
    </FormField>
  );
}
