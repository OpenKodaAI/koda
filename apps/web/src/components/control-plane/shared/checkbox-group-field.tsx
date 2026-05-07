"use client";

import { useCallback } from "react";
import { Check } from "lucide-react";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface CheckboxGroupFieldProps {
  label: string;
  description?: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

export function CheckboxGroupField({
  label,
  description,
  options,
  selected,
  onChange,
}: CheckboxGroupFieldProps) {
  const { tl } = useAppI18n();
  const toggle = useCallback(
    (value: string) => {
      if (selected.includes(value)) {
        onChange(selected.filter((v) => v !== value));
      } else {
        onChange([...selected, value]);
      }
    },
    [selected, onChange],
  );

  return (
    <FormField label={label} description={description}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {options.map((opt) => {
          const isChecked = selected.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggle(opt.value)}
              className="flex items-center gap-2 px-3 py-2 rounded border transition-colors text-left"
              style={{
                borderColor: isChecked
                  ? "var(--tone-info-border)"
                  : "var(--border-subtle)",
                backgroundColor: isChecked
                  ? "rgba(76, 127, 209, 0.08)"
                  : "transparent",
              }}
            >
              <span
                className="flex items-center justify-center h-4 w-4 rounded border shrink-0 transition-colors"
                style={{
                  borderColor: isChecked
                    ? "var(--tone-info-border)"
                    : "var(--border-strong)",
                  backgroundColor: isChecked
                    ? "var(--tone-info-bg-strong)"
                    : "transparent",
                }}
              >
                {isChecked && (
                  <Check size={10} className="text-[var(--tone-info-text)]" />
                )}
              </span>
              <span className="text-sm text-[var(--text-secondary)] truncate">
                {tl(opt.label)}
              </span>
            </button>
          );
        })}
      </div>
    </FormField>
  );
}
