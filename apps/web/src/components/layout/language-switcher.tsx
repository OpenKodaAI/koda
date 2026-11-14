"use client";

import { useMemo, useState } from "react";
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
export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, options, setLanguage, t } = useAppI18n();
  const [open, setOpen] = useState(false);

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
        onOpenChange={setOpen}
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
                "h-4 w-4 shrink-0 text-[var(--text-primary)] transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </ActionButton>
        </SelectPrimitive.Trigger>

        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            position="popper"
            side="bottom"
            align="end"
            sideOffset={8}
            collisionPadding={12}
            aria-label={t("language.label")}
            className={cn(
              "app-floating-panel language-switcher__menu",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-1",
            )}
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
                      <SelectPrimitive.ItemText className="language-switcher__option-label">
                        {t(option.labelKey)}
                      </SelectPrimitive.ItemText>
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
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  );
}
