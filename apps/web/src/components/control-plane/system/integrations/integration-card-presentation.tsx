"use client";

import { AlertTriangle, Check, Plus } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export type IntegrationCardVisualStatus =
  | "connected"
  | "pending"
  | "disconnected";

export function integrationCardRootClassName(
  status: IntegrationCardVisualStatus,
) {
  return cn(
    "integration-card group relative flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-220",
    "cursor-pointer outline-none",
    "focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]",
    status === "connected"
      ? "integration-card--connected border-transparent"
      : "border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]",
  );
}

export function IntegrationCardStatusIndicator({
  status,
}: {
  status: IntegrationCardVisualStatus;
}) {
  if (status === "connected") {
    return (
      <motion.div
        initial={{ scale: 0.82, opacity: 0.72 }}
        animate={{ scale: 1, opacity: 1 }}
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]"
      >
        <Check size={17} />
      </motion.div>
    );
  }

  if (status === "pending") {
    return (
      <div className="flex h-7 w-7 items-center justify-center rounded-full border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]">
        <AlertTriangle size={12} />
      </div>
    );
  }

  return (
    <div className="flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--icon-secondary)] transition-colors group-hover:border-[var(--border-strong)] group-hover:bg-[var(--surface-hover)] group-hover:text-[var(--icon-primary)]">
      <Plus size={14} />
    </div>
  );
}
