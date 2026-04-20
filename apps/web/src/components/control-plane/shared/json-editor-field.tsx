"use client";

import { useCallback, useState } from "react";
import { FormField } from "./form-field";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface JsonEditorFieldProps {
  label: string;
  description?: string;
  value: string;
  onChange: (value: string) => void;
  minHeight?: string;
  compact?: boolean;
}

export function JsonEditorField({
  label,
  description,
  value,
  onChange,
  minHeight,
  compact = true,
}: JsonEditorFieldProps) {
  const { tl } = useAppI18n();
  const [error, setError] = useState<string | null>(null);

  const isValid = (() => {
    const trimmed = value.trim();
    if (!trimmed) return true;
    try {
      JSON.parse(trimmed);
      return true;
    } catch {
      return false;
    }
  })();

  const handleFormat = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;

    try {
      const parsed = JSON.parse(trimmed);
      const formatted = JSON.stringify(parsed, null, 2);
      onChange(formatted);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : tl("Invalid JSON"));
    }
  }, [value, onChange, tl]);

  const handleChange = useCallback(
    (newValue: string) => {
      onChange(newValue);
      // Clear error when user starts editing
      if (error) setError(null);
    },
    [onChange, error],
  );

  const resolvedMinHeight =
    minHeight ?? (compact ? "220px" : "280px");

  return (
    <FormField label={label} description={description} error={error ?? undefined}>
      <div className="relative">
        <textarea
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="field-shell resize-y font-mono text-xs text-[var(--text-primary)]"
          style={{ minHeight: resolvedMinHeight }}
          spellCheck={false}
        />

        {/* Toolbar */}
        <div className="flex items-center gap-3 mt-2">
          {/* Validation indicator */}
          <div className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{
                backgroundColor: value.trim()
                  ? isValid
                    ? "var(--tone-success-dot)"
                    : "var(--tone-danger-dot)"
                  : "var(--text-quaternary)",
              }}
              aria-hidden="true"
            />
            <span className="text-xs text-[var(--text-quaternary)]">
              {value.trim()
                ? isValid
                  ? tl("Valid JSON")
                  : tl("Invalid JSON")
                : tl("Empty")}
            </span>
          </div>

          <div className="flex-1" />

          {/* Format button */}
          <button
            type="button"
            onClick={handleFormat}
            className="button-shell button-shell--secondary button-shell--sm"
          >
            <span>{tl("Format")}</span>
          </button>
        </div>

        {/* Error detail */}
        {!isValid && value.trim() && !error && (
          <p className="mt-1 text-xs text-[var(--tone-danger-text)]">
            {tl("JSON syntax error detected")}
          </p>
        )}
      </div>
    </FormField>
  );
}
