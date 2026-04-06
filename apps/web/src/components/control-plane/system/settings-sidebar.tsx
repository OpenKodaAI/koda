"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { User, Cpu, Plug, Brain, Key } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { SETTINGS_SECTIONS, STEP_TO_SECTION, type SettingsSectionId } from "@/lib/system-settings-model";
import { SettingsWarningIndicator } from "@/components/control-plane/system/settings-warning-indicator";

const SECTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  User, Cpu, Plug, Brain, Key,
};

export function SettingsSidebar() {
  const pathname = usePathname();
  const { t } = useAppI18n();
  const { isDirty, draft } = useSystemSettings();

  const currentSection = pathname.split("/").pop() as SettingsSectionId;

  // Filter out hidden sections per backend config
  const hiddenSections = draft.review?.hidden_sections ?? [];
  const visibleSections = SETTINGS_SECTIONS.filter((s) => {
    const hiddenSectionIds = hiddenSections.map((h) => STEP_TO_SECTION[h] ?? h);
    return !hiddenSectionIds.includes(s.id);
  });

  return (
    <>
      {/* Desktop sidebar */}
      <nav className="hidden md:flex w-[200px] shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3 overflow-visible">
        {visibleSections.map((section) => {
          const Icon = SECTION_ICONS[section.icon];
          const isActive = currentSection === section.id;
          const hasDirty = isDirty(section.id);

          return (
            <Link
              key={section.id}
              href={`/control-plane/system/${section.id}`}
              className={[
                "group flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-[var(--surface-tint-strong)] text-[var(--text-primary)] font-medium"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-tint)] hover:text-[var(--text-primary)]",
              ].join(" ")}
            >
              {Icon && (
                <Icon
                  className={
                    isActive
                      ? "h-4 w-4 shrink-0 text-[var(--icon-primary)]"
                      : "h-4 w-4 shrink-0 text-[var(--icon-secondary)] transition-colors group-hover:text-[var(--icon-primary)]"
                  }
                />
              )}
              <span className="truncate">{t(section.labelKey)}</span>
              {hasDirty && (
                <span className="ml-auto h-2 w-2 shrink-0 rounded-full bg-[var(--interactive-active-border)]" />
              )}
            </Link>
          );
        })}
        <SettingsWarningIndicator className="mt-auto" />
      </nav>

      {/* Mobile tabs */}
      <nav className="flex md:hidden overflow-x-auto overflow-y-visible border-b border-[var(--border-subtle)] px-2">
        {visibleSections.map((section) => {
          const isActive = currentSection === section.id;
          const hasDirty = isDirty(section.id);

          return (
            <Link
              key={section.id}
              href={`/control-plane/system/${section.id}`}
              className={[
                "relative flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-xs font-medium transition-colors",
                isActive
                  ? "text-[var(--text-primary)] border-b-2 border-[var(--interactive-active-border)]"
                  : "text-[var(--text-tertiary)]",
              ].join(" ")}
            >
              {t(section.labelKey)}
              {hasDirty && (
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--interactive-active-border)]" />
              )}
            </Link>
          );
        })}
        <SettingsWarningIndicator compact className="ml-auto self-center" />
      </nav>
    </>
  );
}
