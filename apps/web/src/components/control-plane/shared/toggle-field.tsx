"use client";

import { useId } from "react";
import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface ToggleFieldProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function ToggleField({
  label,
  description,
  checked,
  onChange,
  disabled = false,
}: ToggleFieldProps) {
  const descId = useId();
  const { tl } = useAppI18n();
  const translatedLabel = tl(label);
  const translatedDescription = description ? tl(description) : undefined;

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={translatedLabel}
      aria-describedby={translatedDescription ? descId : undefined}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex items-center justify-between gap-3 w-full py-2.5 group text-left rounded-md px-1 -mx-1 transition-colors hover:bg-[var(--surface-hover)]"
      style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
    >
      {/* Label + description */}
      <span className="flex flex-col min-w-0">
        <span className="text-sm font-medium text-[var(--text-primary)]">{translatedLabel}</span>
        {translatedDescription && (
          <span id={descId} className="text-xs text-[var(--text-quaternary)] leading-relaxed">
            {translatedDescription}
          </span>
        )}
      </span>

      {/* Track */}
      <span
        className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200"
        style={{
          backgroundColor: checked
            ? "var(--tone-success-bg-strong)"
            : "var(--field-bg)",
        }}
      >
        {/* Knob */}
        <motion.span
          className="inline-block h-5 w-5 rounded-full bg-[var(--text-primary)] shadow-sm"
          style={{ marginTop: 2 }}
          animate={{ x: checked ? 22 : 2 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        />
      </span>
    </button>
  );
}
