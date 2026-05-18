"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  CheckCircle2,
  ChevronLeft,
  LoaderCircle,
  Plus,
  TriangleAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface Card {
  id: string;
  title: string;
  status: "completed" | "updates-found" | "syncing";
}

interface AnimatedCardStatusListProps {
  title?: string;
  cards?: Card[];
  onSynchronize?: (cardId: string) => void;
  onAddCard?: () => void;
  onBack?: () => void;
  className?: string;
  synchronizeLabel?: string;
  sort?: "completed-first" | "attention-first" | "stable";
}

const defaultCards: Card[] = [
  { id: "1", title: "Import products from your store", status: "completed" },
  { id: "2", title: "Unique selling points", status: "completed" },
  { id: "3", title: "Primary customers", status: "completed" },
  { id: "4", title: "Common words & phrases", status: "updates-found" },
  { id: "5", title: "Company overview and offer details", status: "syncing" },
];

const STATUS_RANK_ATTENTION: Record<Card["status"], number> = {
  "updates-found": 0,
  syncing: 1,
  completed: 2,
};

const STATUS_RANK_COMPLETED: Record<Card["status"], number> = {
  completed: 0,
  "updates-found": 1,
  syncing: 2,
};

function sortCards(cards: Card[], sort: AnimatedCardStatusListProps["sort"]) {
  if (sort === "stable") return cards;
  const rank = sort === "attention-first" ? STATUS_RANK_ATTENTION : STATUS_RANK_COMPLETED;
  return [...cards].sort((left, right) => rank[left.status] - rank[right.status]);
}

function StatusIcon({
  status,
  reduceMotion,
}: {
  status: Card["status"];
  reduceMotion: boolean;
}) {
  if (status === "completed") {
    return (
      <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--tone-success-dot)] text-[var(--accent-text)]">
        <CheckCircle2 className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
      </span>
    );
  }
  if (status === "updates-found") {
    return (
      <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--tone-warning-dot)] text-[var(--accent-text)]">
        <TriangleAlert className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
      </span>
    );
  }
  return (
    <LoaderCircle
      className={cn("h-4 w-4 text-[var(--tone-info-text)]", !reduceMotion && "animate-spin")}
      strokeWidth={1.75}
      aria-hidden="true"
    />
  );
}
function getStatusText(status: Card["status"]) {
  if (status === "updates-found") return "UPDATES FOUND";
  if (status === "syncing") return "SYNCING";
  return null;
}

function getStatusGradient(status: Card["status"]) {
  if (status === "updates-found") {
    return "from-[var(--tone-warning-bg)] to-transparent";
  }
  if (status === "syncing") {
    return "from-[var(--tone-info-bg)] to-transparent";
  }
  return "";
}

export function AnimatedCardStatusList({
  title = "Fundamentals",
  cards: initialCards = defaultCards,
  onSynchronize,
  onAddCard,
  onBack,
  className = "",
  synchronizeLabel = "Synchronize",
  sort = "completed-first",
}: AnimatedCardStatusListProps = {}) {
  const [cards, setCards] = useState<Card[]>(initialCards);
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const shouldReduceMotion = Boolean(useReducedMotion());
  const showHeaderActions = Boolean(onBack || onAddCard);

  useEffect(() => {
    setCards(initialCards);
  }, [initialCards]);

  const sortedCards = useMemo(() => sortCards(cards, sort), [cards, sort]);

  const handleSynchronize = (cardId: string) => {
    onSynchronize?.(cardId);
    setCards((current) =>
      current.map((card) =>
        card.id === cardId ? { ...card, status: "syncing" as const } : card,
      ),
    );

    window.setTimeout(() => {
      setCards((current) =>
        current.map((card) =>
          card.id === cardId ? { ...card, status: "completed" as const } : card,
        ),
      );
    }, shouldReduceMotion ? 400 : 2500);
  };

  return (
    <section
      className={cn("w-full", className)}
      aria-label={title}
      data-testid="animated-card-status-list"
    >
      <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-4 shadow-none">
        <div
          className={cn(
            "mb-4 flex items-center gap-3",
            showHeaderActions ? "justify-between" : "justify-start",
          )}
        >
          {onBack ? (
            <motion.button
              type="button"
              onClick={onBack}
              className="button-shell button-shell--secondary button-shell--sm h-8 w-8 p-0"
              whileHover={shouldReduceMotion ? undefined : { y: -1 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.98 }}
              aria-label="Back"
            >
              <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
            </motion.button>
          ) : null}

          <h2 className="m-0 min-w-0 flex-1 truncate text-[0.9375rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            {title}
          </h2>

          {onAddCard ? (
            <motion.button
              type="button"
              onClick={onAddCard}
              className="button-shell button-shell--secondary button-shell--sm h-8 w-8 p-0"
              whileHover={shouldReduceMotion ? undefined : { y: -1 }}
              whileTap={shouldReduceMotion ? undefined : { scale: 0.98 }}
              aria-label="Add card"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
            </motion.button>
          ) : null}
        </div>

        <motion.div
          className="space-y-2.5"
          variants={{
            visible: {
              transition: {
                staggerChildren: shouldReduceMotion ? 0 : 0.05,
                delayChildren: shouldReduceMotion ? 0 : 0.05,
              },
            },
          }}
          initial="hidden"
          animate="visible"
        >
          <AnimatePresence initial={false}>
            {sortedCards.map((card) => {
              const statusText = getStatusText(card.status);
              const canSynchronize = Boolean(onSynchronize) && card.status === "updates-found";
              return (
                <motion.div
                  key={card.id}
                  layout
                  variants={{
                    hidden: { opacity: 0, y: shouldReduceMotion ? 0 : 8 },
                    visible: {
                      opacity: 1,
                      y: 0,
                      transition: { duration: shouldReduceMotion ? 0.01 : 0.16 },
                    },
                  }}
                  exit={{ opacity: 0, y: shouldReduceMotion ? 0 : -8 }}
                  transition={{
                    layout: {
                      type: shouldReduceMotion ? false : "spring",
                      stiffness: 420,
                      damping: 34,
                    },
                  }}
                  className="relative"
                  onMouseEnter={() => setHoveredCard(card.id)}
                  onMouseLeave={() => setHoveredCard(null)}
                  data-card-status={card.status}
                >
                  <motion.div
                    className="relative overflow-hidden rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-3"
                    whileHover={shouldReduceMotion ? undefined : { y: -1 }}
                  >
                    {card.status !== "completed" ? (
                      <div
                        className={cn("pointer-events-none absolute inset-0 bg-gradient-to-l", getStatusGradient(card.status))}
                        style={{
                          backgroundSize: "44% 100%",
                          backgroundPosition: "right",
                          backgroundRepeat: "no-repeat",
                        }}
                      />
                    ) : null}

                    <div className="relative flex min-w-0 items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden">
                          <AnimatePresence mode="wait" initial={false}>
                            <motion.span
                              key={card.status}
                              initial={{ opacity: 0, scale: 0.85 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.85 }}
                              transition={{ duration: shouldReduceMotion ? 0.01 : 0.14 }}
                            >
                              <StatusIcon status={card.status} reduceMotion={shouldReduceMotion} />
                            </motion.span>
                          </AnimatePresence>
                        </span>
                        <span className="min-w-0 truncate text-[0.8125rem] text-[var(--text-primary)]">
                          {card.title}
                        </span>
                      </div>

                      <div className="flex h-7 shrink-0 items-center">
                        <AnimatePresence mode="wait" initial={false}>
                          {canSynchronize && hoveredCard === card.id ? (
                            <motion.button
                              key="sync-button"
                              type="button"
                              onClick={() => handleSynchronize(card.id)}
                              className="button-shell button-shell--secondary button-shell--sm h-7 px-2.5 text-[0.6875rem]"
                              initial={{ opacity: 0, scale: 0.92 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.92 }}
                              transition={{ duration: shouldReduceMotion ? 0.01 : 0.12 }}
                            >
                              {synchronizeLabel}
                            </motion.button>
                          ) : statusText ? (
                            <motion.span
                              key="status-text"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              exit={{ opacity: 0 }}
                              className="whitespace-nowrap font-mono text-[0.625rem] font-medium tracking-[var(--tracking-mono)] text-[var(--text-tertiary)]"
                            >
                              {statusText}
                            </motion.span>
                          ) : null}
                        </AnimatePresence>
                      </div>
                    </div>
                  </motion.div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </motion.div>
      </div>
    </section>
  );
}
