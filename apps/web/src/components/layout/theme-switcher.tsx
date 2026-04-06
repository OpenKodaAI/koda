"use client";

import {
  startTransition,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, LaptopMinimal, MoonStar, SunMedium, type LucideIcon } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useTheme } from "@/hooks/use-theme";
import { cn } from "@/lib/utils";

type ThemePreference = "system" | "light" | "dark";

type ThemeOption = {
  value: ThemePreference;
  labelKey: string;
  icon: LucideIcon;
};

const THEME_OPTIONS: ThemeOption[] = [
  { value: "system", labelKey: "theme.options.system", icon: LaptopMinimal },
  { value: "light", labelKey: "theme.options.light", icon: SunMedium },
  { value: "dark", labelKey: "theme.options.dark", icon: MoonStar },
];

export function ThemeSwitcher({ className }: { className?: string }) {
  const { t } = useAppI18n();
  const { themePreference, setThemePreference } = useTheme();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  const currentOption =
    THEME_OPTIONS.find((option) => option.value === themePreference) ?? THEME_OPTIONS[0];

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
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
    if (!open) {
      return;
    }

    const updatePosition = () => {
      if (!rootRef.current) {
        return;
      }

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

  useEffect(() => {
    if (!open) {
      return;
    }

    const activeIndex = THEME_OPTIONS.findIndex((option) => option.value === themePreference);
    const indexToFocus = activeIndex >= 0 ? activeIndex : 0;

    const frame = window.requestAnimationFrame(() => {
      optionRefs.current[indexToFocus]?.focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [open, themePreference]);

  const selectPreference = (nextPreference: ThemePreference) => {
    startTransition(() => {
      setThemePreference(nextPreference);
    });
    setOpen(false);
    triggerRef.current?.focus();
  };

  const focusOption = (index: number) => {
    const boundedIndex = (index + THEME_OPTIONS.length) % THEME_OPTIONS.length;
    optionRefs.current[boundedIndex]?.focus();
  };

  const handlePanelKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const focusedIndex = optionRefs.current.findIndex((option) => option === document.activeElement);

    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusOption((focusedIndex >= 0 ? focusedIndex : 0) + 1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      focusOption((focusedIndex >= 0 ? focusedIndex : 0) - 1);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      focusOption(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      focusOption(THEME_OPTIONS.length - 1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      const index =
        focusedIndex >= 0
          ? focusedIndex
          : THEME_OPTIONS.findIndex((option) => option.value === themePreference);
      const option = THEME_OPTIONS[index >= 0 ? index : 0];
      event.preventDefault();
      selectPreference(option.value);
    }
  };

  return (
    <div
      ref={rootRef}
      className={cn("theme-switcher relative", className)}
      {...tourAnchor("shell.topbar.theme-switcher")}
    >
      <ActionButton
        ref={triggerRef}
        type="button"
        className={cn(
          "workspace-topbar__tool theme-switcher__trigger",
          open && "workspace-topbar__tool--active",
        )}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t("theme.label")}
        title={t("theme.label")}
        {...tourAnchor("shell.topbar.theme-switcher.trigger")}
      >
        <span className="inline-flex min-w-0 items-center gap-2">
          {currentOption.icon ? (
            <currentOption.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : null}
          <span className="hidden truncate sm:inline">{t(currentOption.labelKey)}</span>
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
                  aria-label={t("theme.label")}
                  onKeyDown={handlePanelKeyDown}
                  {...tourAnchor("shell.topbar.theme-switcher.menu")}
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
                    {THEME_OPTIONS.map((option, index) => {
                      const isActive = option.value === themePreference;
                      const OptionIcon = option.icon;

                      return (
                        <button
                          key={option.value}
                          ref={(node) => {
                            optionRefs.current[index] = node;
                          }}
                          type="button"
                          role="option"
                          aria-selected={isActive}
                          className={cn(
                            "language-switcher__option",
                            isActive && "language-switcher__option--active",
                          )}
                          onClick={() => selectPreference(option.value)}
                          {...tourAnchor(`shell.topbar.theme-switcher.option.${option.value}`)}
                        >
                          <span className="language-switcher__option-copy">
                            <span className="language-switcher__flag" aria-hidden="true">
                              <OptionIcon className="h-4 w-4" />
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
