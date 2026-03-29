"use client";

import { useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface KVEntry {
  key: string;
  value: string;
}

interface KeyValueEditorProps {
  label: string;
  description?: string;
  entries: KVEntry[];
  onChange: (entries: KVEntry[]) => void;
}

export function KeyValueEditor({
  label,
  description,
  entries,
  onChange,
}: KeyValueEditorProps) {
  const { tl } = useAppI18n();
  const updateEntry = useCallback(
    (index: number, field: "key" | "value", val: string) => {
      const updated = [...entries];
      updated[index] = { ...updated[index], [field]: val };
      onChange(updated);
    },
    [entries, onChange],
  );

  const addEntry = useCallback(() => {
    onChange([...entries, { key: "", value: "" }]);
  }, [entries, onChange]);

  const removeEntry = useCallback(
    (index: number) => {
      onChange(entries.filter((_, i) => i !== index));
    },
    [entries, onChange],
  );

  return (
    <FormField label={label} description={description}>
      <div className="flex flex-col gap-2">
        {entries.map((entry, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={entry.key}
              onChange={(e) => updateEntry(i, "key", e.target.value)}
              className="field-shell flex-1 px-3 py-2 text-sm text-[var(--text-primary)] font-mono"
              placeholder={tl("chave")}
            />
            <input
              type="text"
              value={entry.value}
              onChange={(e) => updateEntry(i, "value", e.target.value)}
              className="field-shell flex-1 px-3 py-2 text-sm text-[var(--text-primary)]"
              placeholder={tl("valor")}
            />
            <button
              type="button"
              onClick={() => removeEntry(i)}
              className="p-1.5 text-[var(--text-quaternary)] hover:text-[var(--tone-danger-text)] transition-colors"
              aria-label={tl("Remover")}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}

        <button
          type="button"
          onClick={addEntry}
          className="button-shell button-shell--secondary button-shell--sm self-start flex items-center gap-1"
        >
          <Plus size={14} />
          <span>{tl("Adicionar")}</span>
        </button>
      </div>
    </FormField>
  );
}
