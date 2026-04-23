"use client";

import { CheckCircle2, Hand, Ban } from "lucide-react";
import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type ToolPolicy = "always_allow" | "always_ask" | "blocked";

type ToolPolicySegmentProps = {
  value: ToolPolicy;
  onChange: (policy: ToolPolicy) => void;
  disabled?: boolean;
};

/* ------------------------------------------------------------------ */
/*  Policy option config                                               */
/* ------------------------------------------------------------------ */

const POLICY_OPTIONS = [
  {
    policy: "always_allow" as const,
    Icon: CheckCircle2,
    activeBg: "rgba(113,219,190,0.15)",
    activeColor: "var(--tone-success-dot)",
    labelKey: "Sempre permitir",
  },
  {
    policy: "always_ask" as const,
    Icon: Hand,
    activeBg: "rgba(255,180,76,0.15)",
    activeColor: "var(--tone-warning-dot)",
    labelKey: "Precisa de aprovacao",
  },
  {
    policy: "blocked" as const,
    Icon: Ban,
    activeBg: "rgba(180,90,105,0.15)",
    activeColor: "var(--tone-danger-dot)",
    labelKey: "Bloqueado",
  },
] as const;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ToolPolicySegment({
  value,
  onChange,
  disabled = false,
}: ToolPolicySegmentProps) {
  const { tl } = useAppI18n();

  return (
    <div className="relative inline-flex rounded-lg border border-[var(--border-subtle)] bg-[rgba(0,0,0,0.25)] p-0.5">
      {/* Animated background indicator */}
      <motion.div
        className="absolute top-0.5 bottom-0.5 rounded-md"
        style={{ backgroundColor: POLICY_OPTIONS.find((o) => o.policy === value)?.activeBg }}
        initial={false}
        animate={{
          x: POLICY_OPTIONS.findIndex((o) => o.policy === value) * 32 + 0,
          width: 32,
        }}
        transition={{ type: "spring", stiffness: 400, damping: 28 }}
      />
      {POLICY_OPTIONS.map(({ policy, Icon, activeColor, labelKey }) => {
        const isActive = value === policy;

        return (
          <button
            key={policy}
            type="button"
            disabled={disabled}
            onClick={() => onChange(policy)}
            aria-label={tl(labelKey)}
            aria-pressed={isActive}
            className={cn(
              "relative z-10 flex h-7 w-8 items-center justify-center rounded-md transition-colors duration-150",
              !isActive && "text-[var(--text-quaternary)] hover:text-[var(--text-tertiary)]",
              disabled && "pointer-events-none opacity-40",
            )}
          >
            <Icon
              size={14}
              style={{ color: isActive ? activeColor : undefined }}
            />
          </button>
        );
      })}
    </div>
  );
}
