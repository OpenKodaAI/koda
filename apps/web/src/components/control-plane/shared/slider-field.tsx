"use client";

import { useMemo } from "react";
import { FormField } from "./form-field";

interface SliderFieldProps {
  label: string;
  description?: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
  labels?: string[];
  /** Show the numeric value next to the slider */
  showValue?: boolean;
}

export function SliderField({
  label,
  description,
  min,
  max,
  step = 1,
  value,
  onChange,
  labels,
  showValue = true,
}: SliderFieldProps) {
  const pct = ((value - min) / (max - min)) * 100;

  // Calculate which label is currently active
  const activeLabel = useMemo(() => {
    if (!labels || labels.length === 0) return null;
    const idx = Math.round(((value - min) / (max - min)) * (labels.length - 1));
    return labels[idx] || null;
  }, [value, min, max, labels]);

  return (
    <FormField label={label} description={description}>
      <div className="flex flex-col gap-2.5">
        {/* Active label badge */}
        {activeLabel && (
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center px-2.5 py-1 rounded text-xs font-medium transition-all duration-200"
              style={{
                backgroundColor: "rgba(76, 127, 209, 0.1)",
                color: "var(--tone-info-text)",
                border: "1px solid var(--tone-info-border)",
              }}
            >
              {activeLabel}
            </span>
            {showValue && (
              <span className="text-[10px] font-mono text-[var(--text-quaternary)] tabular-nums">
                ({value})
              </span>
            )}
          </div>
        )}

        {/* Slider */}
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-label={label}
            aria-valuemin={min}
            aria-valuemax={max}
            aria-valuenow={value}
            aria-valuetext={activeLabel ? `${activeLabel} (${value})` : String(value)}
            className="ui-slider flex-1"
            style={{
              background: `linear-gradient(to right, var(--tone-info-bg-strong) ${pct}%, var(--field-bg) ${pct}%)`,
            }}
          />
          {!activeLabel && showValue && (
            <span className="text-sm font-mono text-[var(--text-secondary)] min-w-[3ch] text-right tabular-nums">
              {value}
            </span>
          )}
        </div>

        {/* Labels underneath the slider */}
        {labels && labels.length > 0 && (
          <div className="flex justify-between px-0.5">
            {labels.map((lbl, i) => {
              const isActive = i === Math.round(((value - min) / (max - min)) * (labels.length - 1));
              return (
                <button
                  key={`${lbl}-${i}`}
                  type="button"
                  onClick={() => {
                    const targetValue = min + (i / (labels.length - 1)) * (max - min);
                    onChange(Math.round(targetValue / step) * step);
                  }}
                  className="text-[10px] transition-colors cursor-pointer hover:text-[var(--text-secondary)]"
                  style={{
                    color: isActive ? "var(--text-primary)" : "var(--text-quaternary)",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {lbl}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </FormField>
  );
}
