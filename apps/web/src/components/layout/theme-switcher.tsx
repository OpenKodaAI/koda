"use client";

import { Moon, Sun } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useTheme } from "@/hooks/use-theme";
import { cn } from "@/lib/utils";

function ThemeToggleIcon({ isDark }: { isDark: boolean }) {
  return (
    <span className="theme-toggle__icon-stack" aria-hidden="true">
      <Sun
        className={cn("theme-toggle__icon theme-toggle__icon--sun", !isDark && "is-active")}
        strokeWidth={1.75}
      />
      <Moon
        className={cn("theme-toggle__icon theme-toggle__icon--moon", isDark && "is-active")}
        strokeWidth={1.75}
      />
    </span>
  );
}

export function ThemeSwitcher({ className }: { className?: string }) {
  const { t } = useAppI18n();
  const { theme, setThemePreference } = useTheme();
  const isDark = theme === "dark";

  const nextLabel = t(isDark ? "theme.options.light" : "theme.options.dark");
  const label = `${t("theme.label")}: ${nextLabel}`;

  return (
    <ActionButton
      type="button"
      size="icon"
      leading={<ThemeToggleIcon isDark={isDark} />}
      className={cn("theme-toggle workspace-topbar__tool", className)}
      onClick={() => setThemePreference(isDark ? "light" : "dark")}
      aria-label={label}
      aria-pressed={isDark}
      title={label}
      {...tourAnchor("shell.topbar.theme-switcher")}
    />
  );
}
