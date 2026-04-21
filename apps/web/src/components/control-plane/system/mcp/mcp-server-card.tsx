"use client";

import { Pencil, Trash2, Terminal, Globe } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { AnimatedSwitch } from "@/components/control-plane/system/shared/animated-switch";
import type { McpServerCatalogEntry } from "@/lib/control-plane";
import { MCP_CATEGORY_LABELS, type McpCategory } from "./mcp-catalog-data";

/* ------------------------------------------------------------------ */
/*  Transport badge                                                    */
/* ------------------------------------------------------------------ */

function TransportBadge({ type }: { type: "stdio" | "http_sse" }) {
  const isStdio = type === "stdio";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        isStdio
          ? "border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
          : "border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
      )}
    >
      {isStdio ? <Terminal size={10} /> : <Globe size={10} />}
      {isStdio ? "stdio" : "http"}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  MCP Server Card                                                    */
/* ------------------------------------------------------------------ */

export function McpServerCard({
  server,
  onEdit,
  onDelete,
  onToggle,
}: {
  server: McpServerCatalogEntry;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
}) {
  const { tl } = useAppI18n();
  const categoryLabel =
    MCP_CATEGORY_LABELS[server.category as McpCategory] ?? server.category;

  return (
    <motion.div
      layout
      className={cn(
        "group relative flex w-full flex-col gap-2 rounded-lg border px-4 py-3 transition-all duration-220",
        server.enabled
          ? "border-[var(--tone-success-border)] bg-[var(--surface-elevated)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]",
      )}
      style={
        server.enabled
          ? { borderLeftWidth: 3, borderLeftColor: "var(--tone-success-dot)" }
          : undefined
      }
    >
      {/* Top row: name + badges */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {server.display_name}
            </span>
            <TransportBadge type={server.transport_type} />
          </div>
          <span className="mt-0.5 block text-[10px] uppercase tracking-wider text-[var(--text-quaternary)]">
            {tl(categoryLabel)}
          </span>
        </div>

        <AnimatedSwitch
          checked={server.enabled}
          onChange={onToggle}
          ariaLabel={`${tl("Ativar")} ${server.display_name}`}
        />
      </div>

      {/* Description */}
      {server.description ? (
        <p className="line-clamp-2 text-xs leading-relaxed text-[var(--text-tertiary)]">
          {server.description}
        </p>
      ) : null}

      {/* Actions */}
      <div className="flex items-center gap-1 pt-0.5">
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
          aria-label={`${tl("Editar")} ${server.display_name}`}
        >
          <Pencil size={12} />
          {tl("Editar")}
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="inline-flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-xs text-[var(--tone-danger-text)] transition-colors hover:border-[var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg)]"
          aria-label={`${tl("Remover")} ${server.display_name}`}
        >
          <Trash2 size={12} />
          {tl("Remover")}
        </button>
      </div>
    </motion.div>
  );
}
