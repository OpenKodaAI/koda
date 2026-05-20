"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Copy, LoaderCircle, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import type { ControlPlaneAgentSummary } from "@/lib/control-plane";

interface AgentCatalogCardProps {
  agent: ControlPlaneAgentSummary;
  onDragStart: (id: string, dataTransfer: DataTransfer) => void;
  onDragEnd: () => void;
  busy: boolean;
  isDragging: boolean;
  isMoving: boolean;
  isDuplicating: boolean;
  onEdit: (id: string) => void;
  onDuplicate: (agent: ControlPlaneAgentSummary) => void;
  onRequestDelete: (agent: ControlPlaneAgentSummary) => void;
}

function statusLabel(status: string, t: (key: string) => string): string {
  switch (status) {
    case "active":
      return t("common.active");
    case "paused":
      return t("common.paused");
    default:
      return status;
  }
}

export function AgentCatalogCard({
  agent,
  onDragStart,
  onDragEnd,
  busy,
  isDragging,
  isMoving,
  isDuplicating,
  onEdit,
  onDuplicate,
  onRequestDelete,
}: AgentCatalogCardProps) {
  const { t } = useAppI18n();
  const cardRef = useRef<HTMLElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const readableStatus = statusLabel(agent.status, t);
  const defaultModel =
    agent.default_model_label || agent.default_model_id || t("generated.controlPlane.sem_modelo_definido_95c40cbd");
  const orbColor = agent.appearance?.color || "#A7ADB4";

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!cardRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <article
      ref={cardRef}
      draggable={!busy && !menuOpen}
      data-testid={`agent-card-${agent.id}`}
      onDragStart={(event) => {
        setMenuOpen(false);
        onDragStart(agent.id, event.dataTransfer);
      }}
      onDragEnd={onDragEnd}
      className={`agent-board-card group relative flex w-full cursor-grab flex-col rounded-[0.5rem] transition-[opacity,transform,background-color,border-color,box-shadow] duration-200 active:cursor-grabbing ${isDragging ? "agent-board-card--dragging" : ""} ${isMoving ? "pointer-events-none" : ""}`}
      aria-label={`${t("generated.controlPlane.agente_794b0ee3")} ${agent.display_name}`}
    >
      {isMoving ? (
        <>
          <div className="pointer-events-none absolute inset-0 rounded-[0.5rem] bg-[var(--surface-hover)]" />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px overflow-hidden rounded-full bg-[var(--border-subtle)]">
            <span className="block h-full w-1/3 animate-[agentMoveBar_1s_ease-in-out_infinite] rounded-full bg-[var(--button-primary-bg)]" />
          </div>
          <span className="pointer-events-none absolute right-3 top-3 inline-flex items-center gap-1 rounded-[0.5rem] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            {t("generated.controlPlane.movendo_20da2807")}
          </span>
        </>
      ) : null}

            <div className="agent-board-card__row flex items-center gap-2 px-2.5 py-1 sm:px-3">
        <span
          className="flex-shrink-0"
          title={readableStatus}
        >
          <AgentSigil
            agentId={agent.id}
            label={agent.display_name || agent.id}
            color={orbColor}
            status={agent.status}
            size="sm"
          />
          <span className="sr-only">
            {t("generated.controlPlane.status_d22fba71")}: {readableStatus}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <h3 className="min-w-0">
                <Link
                  href={`/control-plane/agents/${agent.id}`}
                  className="block min-w-0 truncate whitespace-nowrap text-[0.9375rem] font-medium leading-tight tracking-[-0.02em] text-[var(--text-primary)] transition-opacity duration-200 hover:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-0 group-hover:opacity-100"
                  title={agent.display_name}
                >
                  <span className="block">
                    {agent.display_name}
                  </span>
                </Link>
              </h3>
              <p
                className="truncate whitespace-nowrap text-[0.8125rem] leading-5 text-[var(--text-tertiary)]"
                title={defaultModel}
              >
                {defaultModel}
              </p>
            </div>

            <div className="agent-board-card__actions flex flex-shrink-0 items-center gap-2 self-center">
              <ActionButton
                type="button"
                size="icon"
                className={cn(
                  "agent-board-card__menu-trigger",
                  menuOpen && "agent-board-card__menu-trigger--active",
                )}
                aria-label={`${t("generated.controlPlane.abrir_acoes_do_agente_4cc708f1")} ${agent.display_name}`}
                aria-expanded={menuOpen}
                aria-haspopup="menu"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  setMenuOpen((current) => !current);
                }}
                disabled={busy}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </ActionButton>

              <AnimatePresence>
                {menuOpen ? (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                    className="app-floating-surface agent-board-card__menu"
                    role="menu"
                    onPointerDown={(event) => event.stopPropagation()}
                  >
                    <button
                      type="button"
                      className="agent-board-card__menu-action"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        onEdit(agent.id);
                      }}
                      disabled={busy}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      {t("generated.controlPlane.editar_28e2e08e")}
                    </button>
                    <button
                      type="button"
                      className="agent-board-card__menu-action"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        onDuplicate(agent);
                      }}
                      disabled={busy || isDuplicating}
                    >
                      {isDuplicating ? (
                        <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                      {t("generated.controlPlane.duplicar_7242c740")}
                    </button>
                    <button
                      type="button"
                      className="agent-board-card__menu-action agent-board-card__menu-action--danger"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        onRequestDelete(agent);
                      }}
                      disabled={busy}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      {t("generated.controlPlane.excluir_687a343e")}
                    </button>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
