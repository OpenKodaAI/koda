"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { AppLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LANGUAGE_SHORT_LABELS: Record<AppLanguage, string> = {
  "en-US": "EN",
  "pt-BR": "PT-BR",
  "es-ES": "ES",
  "fr-FR": "FR",
  "de-DE": "DE",
};

const LANGUAGE_FLAGS: Record<AppLanguage, string> = {
  "en-US": "🇺🇸",
  "pt-BR": "🇧🇷",
  "es-ES": "🇪🇸",
  "fr-FR": "🇫🇷",
  "de-DE": "🇩🇪",
};

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, options, setLanguage, t } = useAppI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  const currentOption = useMemo(
    () => options.find((option) => option.value === language) ?? options[0],
    [language, options],
  );

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      if (!rootRef.current) return;

      const triggerRect = rootRef.current.getBoundingClientRect();
      const viewportPadding = 12;
      const width = Math.min(176, window.innerWidth - viewportPadding * 2);
      const left = Math.min(
        Math.max(triggerRect.right - width, viewportPadding),
        window.innerWidth - viewportPadding - width,
      );

      setPanelPosition({
        top: triggerRect.bottom + 8,
        left,
        width,
      });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      className={cn("language-switcher relative", className)}
      {...tourAnchor("shell.topbar.language-switcher")}
    >
      <ActionButton
        type="button"
        className={cn(
          "workspace-topbar__tool language-switcher__trigger",
          open && "workspace-topbar__tool--active",
        )}
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t("language.label")}
        {...tourAnchor("shell.topbar.language-switcher.trigger")}
      >
        <span className="language-switcher__value">
          <span className="language-switcher__flag" aria-hidden="true">
            {LANGUAGE_FLAGS[currentOption.value]}
          </span>
          <span className="truncate">
            {LANGUAGE_SHORT_LABELS[currentOption.value]}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-[var(--text-primary)] transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </ActionButton>

      {typeof document !== "undefined"
        ? createPortal(
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  ref={panelRef}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  className="app-floating-panel language-switcher__menu"
                  role="listbox"
                  aria-label={t("language.label")}
                  {...tourAnchor("shell.topbar.language-switcher.menu")}
                  style={{
                    position: "fixed",
                    zIndex: 80,
                    top: panelPosition?.top ?? 0,
                    left: panelPosition?.left ?? 0,
                    width: panelPosition?.width,
                    visibility: panelPosition ? "visible" : "hidden",
                  }}
                >
                  <div className="language-switcher__menu-list">
                    {options.map((option) => {
                      const isActive = option.value === language;

                      return (
                        <button
                          key={option.value}
                          type="button"
                          role="option"
                          aria-selected={isActive}
                          className={cn(
                            "language-switcher__option",
                            isActive && "language-switcher__option--active",
                          )}
                          onClick={() => {
                            setLanguage(option.value as AppLanguage);
                            setOpen(false);
                          }}
                          {...tourAnchor(`shell.topbar.language-switcher.option.${option.value}`)}
                        >
                          <span className="language-switcher__option-copy">
                            <span className="language-switcher__flag" aria-hidden="true">
                              {LANGUAGE_FLAGS[option.value as AppLanguage]}
                            </span>
                            <span className="language-switcher__option-label">
                              {t(option.labelKey)}
                            </span>
                          </span>
                          <span
                            aria-hidden="true"
                            className={cn(
                              "language-switcher__option-dot",
                              isActive && "language-switcher__option-dot--active",
                            )}
                          />
                        </button>
                      );
                    })}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}
    </div>
  );
}
