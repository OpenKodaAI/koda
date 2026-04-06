"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Copy, LoaderCircle, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";
import type { ControlPlaneBotSummary } from "@/lib/control-plane";

interface BotCatalogCardProps {
  bot: ControlPlaneBotSummary;
  onDragStart: (id: string, dataTransfer: DataTransfer) => void;
  onDragEnd: () => void;
  busy: boolean;
  isDragging: boolean;
  isMoving: boolean;
  isDuplicating: boolean;
  onEdit: (id: string) => void;
  onDuplicate: (bot: ControlPlaneBotSummary) => void;
  onRequestDelete: (bot: ControlPlaneBotSummary) => void;
}

function statusLabel(status: string): string {
  switch (status) {
    case "active":
      return "Ativo";
    case "paused":
      return "Pausado";
    default:
      return status;
  }
}

function statusTone(status: string): string {
  switch (status) {
    case "active":
      return "var(--tone-success-dot)";
    case "paused":
      return "var(--tone-warning-dot)";
    default:
      return "var(--tone-neutral-dot)";
  }
}

export function BotCatalogCard({
  bot,
  onDragStart,
  onDragEnd,
  busy,
  isDragging,
  isMoving,
  isDuplicating,
  onEdit,
  onDuplicate,
  onRequestDelete,
}: BotCatalogCardProps) {
  const { tl } = useAppI18n();
  const cardRef = useRef<HTMLElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const readableStatus = tl(statusLabel(bot.status));
  const statusColor = statusTone(bot.status);
  const defaultModel =
    bot.default_model_label || bot.default_model_id || tl("Sem modelo definido");
  const orbColor =
    bot.appearance?.color ||
    bot.organization?.squad_color ||
    bot.organization?.workspace_color ||
    "#A7ADB4";

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
      data-testid={`bot-card-${bot.id}`}
      onDragStart={(event) => {
        setMenuOpen(false);
        onDragStart(bot.id, event.dataTransfer);
      }}
      onDragEnd={onDragEnd}
      className={`agent-board-card group relative flex w-full cursor-grab flex-col rounded-[0.5rem] transition-[opacity,transform,background-color,border-color,box-shadow] duration-200 active:cursor-grabbing ${isDragging ? "agent-board-card--dragging" : ""} ${isMoving ? "pointer-events-none" : ""}`}
      aria-label={`${tl("Agente")} ${bot.display_name}`}
    >
      {isMoving ? (
        <>
          <div className="pointer-events-none absolute inset-0 rounded-[0.5rem] bg-[var(--surface-hover)]" />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px overflow-hidden rounded-full bg-[var(--border-subtle)]">
            <span className="block h-full w-1/3 animate-[botMoveBar_1s_ease-in-out_infinite] rounded-full bg-[var(--button-primary-bg)]" />
          </div>
          <span className="pointer-events-none absolute right-3 top-3 inline-flex items-center gap-1 rounded-[0.5rem] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            {tl("Movendo")}
          </span>
        </>
      ) : null}

            <div className="agent-board-card__row flex items-start gap-3 px-3 py-3 sm:px-3.5">
        <span
          className="agent-board-card__orb-shell inline-flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-[0.8rem]"
          title={readableStatus}
        >
          <BotAgentGlyph
            botId={bot.id}
            color={orbColor}
            className="agent-board-card__orb h-11 w-11 bot-swatch--animated rounded-[0.72rem]"
            active={bot.status === "active"}
            variant="card"
            shape="swatch"
          />
          <span
            aria-hidden="true"
            className="agent-board-card__status-indicator"
            style={{ backgroundColor: statusColor }}
          />
          <span className="sr-only">
            {tl("Status")}: {readableStatus}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <h3 className="min-w-0">
                <Link
                  href={`/control-plane/bots/${bot.id}`}
                  className="block min-w-0 truncate whitespace-nowrap text-[1rem] font-semibold leading-tight tracking-[-0.03em] text-[var(--text-primary)] transition-opacity duration-200 hover:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-0 group-hover:opacity-100"
                  title={bot.display_name}
                >
                  <span className="block">
                    {bot.display_name}
                  </span>
                </Link>
              </h3>
              <p
                className="truncate whitespace-nowrap text-[0.92rem] leading-6 text-[var(--text-secondary)]"
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
                aria-label={`${tl("Abrir ações do agente")} ${bot.display_name}`}
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
                        onEdit(bot.id);
                      }}
                      disabled={busy}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      {tl("Editar")}
                    </button>
                    <button
                      type="button"
                      className="agent-board-card__menu-action"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        onDuplicate(bot);
                      }}
                      disabled={busy || isDuplicating}
                    >
                      {isDuplicating ? (
                        <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                      {tl("Duplicar")}
                    </button>
                    <button
                      type="button"
                      className="agent-board-card__menu-action agent-board-card__menu-action--danger"
                      role="menuitem"
                      onClick={() => {
                        setMenuOpen(false);
                        onRequestDelete(bot);
                      }}
                      disabled={busy}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      {tl("Excluir")}
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
