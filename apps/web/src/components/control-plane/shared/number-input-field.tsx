"use client";

import { useCallback } from "react";
import { Minus, Plus } from "lucide-react";
import { FormField } from "./form-field";

interface NumberInputFieldProps {
  label: string;
  description?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}

export function NumberInputField({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
}: NumberInputFieldProps) {
  const clamp = useCallback(
    (v: number) => {
      let clamped = v;
      if (min !== undefined) clamped = Math.max(min, clamped);
      if (max !== undefined) clamped = Math.min(max, clamped);
      return clamped;
    },
    [min, max],
  );

  const increment = useCallback(() => {
    onChange(clamp(value + step));
  }, [value, step, onChange, clamp]);

  const decrement = useCallback(() => {
    onChange(clamp(value - step));
  }, [value, step, onChange, clamp]);

  return (
    <FormField label={label} description={description}>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={decrement}
          disabled={min !== undefined && value <= min}
          className="inline-flex items-center justify-center h-9 w-9 shrink-0 rounded border border-[var(--border-subtle)] bg-[var(--surface-tint)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label={`Diminuir ${label}`}
        >
          <Minus size={14} />
        </button>

        <div className="flex items-center">
          <input
            type="number"
            value={value}
            onChange={(e) => {
              const parsed = Number(e.target.value);
              if (!isNaN(parsed)) onChange(clamp(parsed));
            }}
            min={min}
            max={max}
            step={step}
            aria-label={label}
            className="field-shell w-20 px-2 py-2 text-sm text-[var(--text-primary)] text-center tabular-nums [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          {unit && (
            <span className="text-xs text-[var(--text-quaternary)] ml-1.5 shrink-0">
              {unit}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={increment}
          disabled={max !== undefined && value >= max}
          className="inline-flex items-center justify-center h-9 w-9 shrink-0 rounded border border-[var(--border-subtle)] bg-[var(--surface-tint)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label={`Aumentar ${label}`}
        >
          <Plus size={14} />
        </button>
      </div>
    </FormField>
  );
}
