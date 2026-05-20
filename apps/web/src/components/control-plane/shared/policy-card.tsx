"use client";

import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, type LucideIcon } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface PolicyCardProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  children: ReactNode;
  defaultOpen?: boolean;
  dirty?: boolean;
  variant?: "card" | "flat";
}

export function PolicyCard({
  title,
  description,
  icon: Icon,
  children,
  defaultOpen = false,
  dirty = false,
  variant = "card",
}: PolicyCardProps) {
  const { tl } = useAppI18n();
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (variant === "flat") {
    const headerContent = (
      <>
        {Icon && (
          <span className="inline-flex shrink-0 items-center justify-center text-[var(--text-quaternary)]">
            <Icon size={14} strokeWidth={1.75} />
          </span>
        )}
        <div className="flex flex-col flex-1 min-w-0 gap-0.5">
          <span className="eyebrow">
            {tl(title)}
          </span>
          {description ? (
            <span className="text-xs text-[var(--text-tertiary)] leading-relaxed">
              {tl(description)}
            </span>
          ) : null}
        </div>
        {dirty ? (
          <span
            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full animate-pulse"
            style={{ backgroundColor: "var(--tone-warning-dot)" }}
            aria-hidden
          />
        ) : null}
      </>
    );

    // When defaultOpen=true we skip the toggle entirely — the section is just a labeled block.
    if (defaultOpen) {
      return (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2.5">{headerContent}</div>
          <div className="flex flex-col gap-6">{children}</div>
        </section>
      );
    }

    // When defaultOpen=false we keep the toggle affordance (chevron) but without the heavy card.
    return (
      <section className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className="flex w-full items-center gap-2.5 text-left transition-colors"
          aria-expanded={isOpen}
        >
          {headerContent}
          <motion.span
            animate={{ rotate: isOpen ? 90 : 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-[var(--text-quaternary)] shrink-0"
          >
            <ChevronRight size={13} />
          </motion.span>
        </button>
        <AnimatePresence initial={false}>
          {isOpen && (
            <motion.div
              key="content"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="flex flex-col gap-6 border-t border-[color:var(--divider-hair)] pt-4">
                {children}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    );
  }

  return (
    <div
      className="overflow-hidden rounded-[1.15rem] border transition-all duration-300"
      style={{
        borderColor: dirty
          ? "rgba(255,255,255,0.16)"
          : "var(--border-subtle)",
        boxShadow: "none",
      }}
    >
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-[rgba(255,255,255,0.02)]"
        aria-expanded={isOpen}
      >
        {Icon && (
          <span className="inline-flex shrink-0 items-center justify-center text-[var(--text-secondary)]">
            <Icon size={16} />
          </span>
        )}

        <div className="flex flex-col flex-1 min-w-0">
          {description ? (
            <>
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                {tl(title)}
              </span>
              <span className="text-base font-semibold leading-6 text-[var(--text-primary)]">
                {tl(description)}
              </span>
            </>
          ) : (
            <span className="text-sm font-semibold leading-6 text-[var(--text-primary)]">
              {tl(title)}
            </span>
          )}
        </div>

        <motion.span
          animate={{ rotate: isOpen ? 90 : 0 }}
          transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="text-[var(--text-quaternary)] shrink-0"
        >
          <ChevronRight size={14} />
        </motion.span>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-6 border-t border-[var(--border-subtle)] px-5 pb-6 pt-4">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
