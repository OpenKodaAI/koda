"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
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

// Built on the Radix Select primitive (M8-E1-T2), which supplies the
// combobox/listbox roles, arrow-key and typeahead navigation, Enter to pick,
// Escape to close, and moves focus into the list and back to the trigger.
const MENU_EXIT_MS = 160;
const MENU_ENTER = ["animate-in", "fade-in-0", "zoom-in-95", "data-[side=bottom]:slide-in-from-top-1"];
const MENU_EXIT = ["animate-out", "fade-out-0", "zoom-out-95", "fill-mode-forwards"];

/**
 * Radix Select unmounts its list the moment it closes, so the exit fade plays
 * on an inert copy of it. Radix has by then returned focus to the trigger and
 * released the page, and the copy takes no keys, clicks or screen-reader focus.
 * Returns a function that removes the copy early.
 */
function fadeOutCopy(content: HTMLElement | null): (() => void) | undefined {
  // The content's parent is Radix's fixed-position popper frame.
  const frame = content?.parentElement;
  if (!content || !frame) return undefined;
  const copy = frame.cloneNode(true) as HTMLElement;
  copy.setAttribute("aria-hidden", "true");
  copy.setAttribute("inert", "");
  for (const node of [copy, ...copy.querySelectorAll("[id], [data-tour-anchor]")]) {
    node.removeAttribute("id");
    node.removeAttribute("data-tour-anchor");
  }
  const menu = copy.firstElementChild as HTMLElement | null;
  // Radix sets pointer-events: auto inline on the list, so both drop it.
  for (const node of [copy, menu]) node?.style.setProperty("pointer-events", "none");
  menu?.classList.remove(...MENU_ENTER);
  menu?.classList.add(...MENU_EXIT);
  document.body.append(copy);
  const timer = window.setTimeout(() => copy.remove(), MENU_EXIT_MS);
  return () => {
    window.clearTimeout(timer);
    copy.remove();
  };
}

/**
 * While the list is open, Radix hides the rest of the page from assistive tech
 * (aria-hidden, marked data-aria-hidden), traps focus and blocks outside clicks,
 * but the hidden controls stay focusable: axe reports aria-hidden-focus on the
 * skip link, the sidebar, the topbar and the main content (D-350). Make the
 * hidden subtrees inert too, and restore only what this set on close. Radix
 * hides the page from an effect after the list mounts, hence the frame.
 */
function useInertWhileOpen(open: boolean) {
  useEffect(() => {
    if (!open) return undefined;
    const madeInert: Element[] = [];
    const frame = window.requestAnimationFrame(() => {
      for (const node of document.querySelectorAll('[data-aria-hidden="true"]')) {
        if (node.hasAttribute("inert")) continue;
        node.setAttribute("inert", "");
        madeInert.push(node);
      }
    });
    return () => {
      window.cancelAnimationFrame(frame);
      for (const node of madeInert) node.removeAttribute("inert");
    };
  }, [open]);
}

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, options, setLanguage, t } = useAppI18n();
  const [open, setOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const removeCopyRef = useRef<(() => void) | undefined>(undefined);

  useEffect(() => () => removeCopyRef.current?.(), []);
  useInertWhileOpen(open);

  const handleOpenChange = (next: boolean) => {
    removeCopyRef.current?.();
    removeCopyRef.current = next ? undefined : fadeOutCopy(contentRef.current);
    setOpen(next);
  };

  const currentOption = useMemo(
    () => options.find((option) => option.value === language) ?? options[0],
    [language, options],
  );

  return (
    <div
      className={cn("language-switcher relative", className)}
      {...tourAnchor("shell.topbar.language-switcher")}
    >
      <SelectPrimitive.Root
        value={currentOption.value}
        onValueChange={(value) => setLanguage(value as AppLanguage)}
        open={open}
        onOpenChange={handleOpenChange}
      >
        <SelectPrimitive.Trigger asChild>
          <ActionButton
            type="button"
            className={cn(
              "workspace-topbar__tool language-switcher__trigger",
              open && "workspace-topbar__tool--active",
            )}
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
              aria-hidden="true"
              className={cn(
                "h-4 w-4 shrink-0 text-[color:var(--text-primary)] transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </ActionButton>
        </SelectPrimitive.Trigger>

        <SelectPrimitive.Portal>
          {/* The list sits in a named landmark (axe region, D-350); closed, the
              region is hidden, since Radix keeps the closed list off the page. */}
          <div role="region" aria-label={t("language.label")} hidden={!open}>
            <SelectPrimitive.Content
              ref={contentRef}
              position="popper"
              side="bottom"
              align="end"
              sideOffset={8}
              collisionPadding={12}
              aria-label={t("language.label")}
              className={cn("app-floating-panel language-switcher__menu", ...MENU_ENTER)}
              {...tourAnchor("shell.topbar.language-switcher.menu")}
            >
              <SelectPrimitive.Viewport className="language-switcher__menu-list">
                {options.map((option) => {
                  const value = option.value as AppLanguage;
                  const isActive = value === currentOption.value;

                  return (
                    <SelectPrimitive.Item
                      key={value}
                      value={value}
                      className={cn(
                        "language-switcher__option",
                        isActive && "language-switcher__option--active",
                      )}
                      {...tourAnchor(`shell.topbar.language-switcher.option.${value}`)}
                    >
                      <span className="language-switcher__option-copy">
                        <span className="language-switcher__flag" aria-hidden="true">
                          {LANGUAGE_FLAGS[value]}
                        </span>
                        {/* ItemText drops className, so the label styles sit on a wrapper. */}
                        <span className="language-switcher__option-label">
                          <SelectPrimitive.ItemText>{t(option.labelKey)}</SelectPrimitive.ItemText>
                        </span>
                      </span>
                      <span
                        aria-hidden="true"
                        className={cn(
                          "language-switcher__option-dot",
                          isActive && "language-switcher__option-dot--active",
                        )}
                      />
                    </SelectPrimitive.Item>
                  );
                })}
              </SelectPrimitive.Viewport>
            </SelectPrimitive.Content>
          </div>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  );
}
