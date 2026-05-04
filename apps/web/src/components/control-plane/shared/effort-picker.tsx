"use client";

import { useId, useMemo } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import { SoftTabs } from "@/components/ui/soft-tabs";

/**
 * Effort capability surface shipped by the backend (catalog DTO).
 * - `enum` kind: discrete values like "low" | "medium" | "high" — render as SoftTabs
 * - `tokens` kind: integer thinking budget — render as range input + numeric input
 */
export type EffortCapability =
  | {
      kind: "enum";
      values: readonly string[];
      defaultValue?: string;
    }
  | {
      kind: "tokens";
      min: number;
      max: number;
      defaultValue?: number;
    };

export interface EffortPickerProps {
  /** Capability declared by the model in the catalog. When undefined, the picker renders nothing. */
  capability: EffortCapability | undefined;
  /** Current value: string for enum kind, integer for tokens. `null` means "inherit". */
  value: string | number | null;
  /** Value the picker would inherit from the parent scope (global default in agent context). */
  inheritedValue?: string | number | null;
  onChange: (next: string | number | null) => void;
  /** Determines whether the "Inherit" toggle is exposed. */
  context: "global" | "agent";
  /** Optional override label for the field title. */
  labelKey?: string;
  readOnly?: boolean;
}

const DEFAULT_LABEL_KEY = "modelEffort.title";
const ENUM_VALUE_LABELS: Record<string, string> = {
  none: "modelEffort.enumNone",
  default: "modelEffort.enumDefault",
  minimal: "modelEffort.enumMinimal",
  low: "modelEffort.enumLow",
  medium: "modelEffort.enumMedium",
  high: "modelEffort.enumHigh",
  xhigh: "modelEffort.enumXHigh",
  max: "modelEffort.enumMax",
};

export function EffortPicker(props: EffortPickerProps) {
  const { capability, value, inheritedValue, onChange, context, labelKey, readOnly } = props;
  const { t } = useAppI18n();
  const inputId = useId();

  const items = useMemo(() => {
    if (!capability || capability.kind !== "enum") return [];
    return capability.values.map((v) => ({
      id: v,
      label: t(ENUM_VALUE_LABELS[v] ?? `modelEffort.enum.${v}`, { defaultValue: v }),
    }));
  }, [capability, t]);

  // Hide entirely when the model has no effort capability — keeps the UI honest.
  if (!capability) return null;

  const isInheriting = value === null && context === "agent";
  const effectiveValue = isInheriting ? (inheritedValue ?? capability.defaultValue ?? null) : value;
  const labelText = t(labelKey ?? DEFAULT_LABEL_KEY);

  return (
    <div className="flex flex-col gap-2">
      <span className="eyebrow flex items-center justify-between gap-2">
        <span>{labelText}</span>
        {context === "agent" && !readOnly && (
          <button
            type="button"
            onClick={() => onChange(isInheriting ? (inheritedValue ?? capability.defaultValue ?? null) : null)}
            className={cn(
              "text-[0.6875rem] font-medium normal-case tracking-normal underline-offset-2",
              "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:underline",
            )}
          >
            {t(isInheriting ? "modelEffort.customValue" : "modelEffort.inheritGlobal")}
          </button>
        )}
      </span>

      {capability.kind === "enum" && (readOnly || capability.values.length <= 1) ? (
        <div className="field-shell min-h-9 bg-[var(--panel-soft)] text-sm text-[var(--text-secondary)]">
          {t(
            ENUM_VALUE_LABELS[String(effectiveValue ?? capability.defaultValue ?? capability.values[0] ?? "")] ??
              `modelEffort.enum.${String(effectiveValue ?? capability.defaultValue ?? "")}`,
            { defaultValue: String(effectiveValue ?? capability.defaultValue ?? capability.values[0] ?? "") },
          )}
        </div>
      ) : capability.kind === "enum" ? (
        <SoftTabs
          items={items}
          value={String(effectiveValue ?? capability.defaultValue ?? items[0]?.id ?? "")}
          onChange={(next) => onChange(next)}
          ariaLabel={labelText}
          className={cn(isInheriting && "opacity-60")}
        />
      ) : (
        <div className="flex items-center gap-3">
          <input
            id={inputId}
            type="range"
            min={capability.min}
            max={capability.max}
            step={Math.max(1, Math.round((capability.max - capability.min) / 100))}
            value={Number(effectiveValue ?? capability.defaultValue ?? capability.min)}
            onChange={(event) => onChange(Number(event.target.value))}
            disabled={readOnly}
            className={cn("h-1 flex-1 cursor-pointer accent-[var(--accent)]", isInheriting && "opacity-60")}
            aria-label={labelText}
          />
          <input
            type="number"
            min={capability.min}
            max={capability.max}
            value={Number(effectiveValue ?? capability.defaultValue ?? capability.min)}
            onChange={(event) => {
              const n = Number(event.target.value);
              if (Number.isFinite(n)) onChange(n);
            }}
            disabled={readOnly}
            className={cn(
              "h-9 w-20 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-2 text-right text-sm font-mono text-[var(--text-primary)]",
              "focus:outline-none focus:ring-1 focus:ring-[var(--accent-muted)]",
              isInheriting && "opacity-60",
            )}
          />
          <span className="text-xs text-[var(--text-quaternary)]">{t("modelEffort.tokensUnit")}</span>
        </div>
      )}

      <p className="text-xs text-[var(--text-quaternary)] leading-relaxed">
        {t(
          capability.kind === "enum"
            ? "modelEffort.descriptionEnum"
            : "modelEffort.descriptionTokens",
        )}
      </p>
    </div>
  );
}
