"use client";

import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface CompactGrantOption {
  value: string;
  label: string;
  status: string;
}

interface CompactGrantToggleProps {
  title: string;
  description?: string;
  options: CompactGrantOption[];
  selected: string[];
  onToggle: (value: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Compact toggle switch                                              */
/* ------------------------------------------------------------------ */

function MiniSwitch({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className="relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200"
      style={{
        backgroundColor: checked
          ? "var(--tone-success-bg-strong)"
          : "var(--field-bg)",
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      <motion.span
        className="inline-block h-4 w-4 rounded-full bg-[var(--text-primary)] shadow-sm"
        style={{ marginTop: 2 }}
        animate={{ x: checked ? 16 : 2 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Status pill                                                        */
/* ------------------------------------------------------------------ */

function StatusPill({ label, tone }: { label: string; tone: "accent" | "neutral" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
        tone === "accent"
          ? "bg-[rgba(113,219,190,0.12)] text-[var(--text-primary)]"
          : "bg-[rgba(255,255,255,0.04)] text-[var(--text-secondary)]",
      )}
    >
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function CompactGrantToggle({
  title,
  description,
  options,
  selected,
  onToggle,
}: CompactGrantToggleProps) {
  const { tl } = useAppI18n();

  const countLabel = tl("{{selected}}/{{total}} concedido(s)", {
    selected: selected.length,
    total: options.length,
  });

  return (
    <section className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-quaternary)]">{description}</p>
        </div>
        <span className="inline-flex items-center rounded-full bg-[rgba(255,255,255,0.04)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
          {countLabel}
        </span>
      </div>

      {/* Items */}
      <div className="mt-3">
        {options.length === 0 ? (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-3 text-xs text-[var(--text-quaternary)]">
            {tl("Nenhum item disponivel.")}
          </div>
        ) : (
          <div className="divide-y divide-[rgba(255,255,255,0.04)]">
            {options.map((option) => {
              const isSelected = selected.includes(option.value);
              const isBlocked =
                option.status === tl("Somente sistema") ||
                option.status === tl("Indisponivel");
              const disabled = !isSelected && isBlocked;

              const pillTone: "accent" | "neutral" =
                option.status === tl("Grantavel") ||
                option.status === tl("Disponivel globalmente")
                  ? "accent"
                  : "neutral";

              return (
                <div
                  key={option.value}
                  className="flex items-center gap-3 py-2"
                  style={{ minHeight: 36 }}
                >
                  {/* Name */}
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--text-primary)]">
                    {option.label}
                  </span>

                  {/* Status pill */}
                  <StatusPill label={option.status} tone={pillTone} />

                  {/* Toggle */}
                  <MiniSwitch
                    checked={isSelected}
                    disabled={disabled}
                    onChange={() => onToggle(option.value)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
