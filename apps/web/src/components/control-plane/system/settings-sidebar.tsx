"use client";

import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { User, Cpu, Plug, Brain, Key } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { SETTINGS_SECTIONS, STEP_TO_SECTION, type SettingsSectionId } from "@/lib/system-settings-model";
import { SettingsWarningIndicator } from "@/components/control-plane/system/settings-warning-indicator";
import { TabBar } from "@/components/control-plane/shared/tab-bar";
import { cn } from "@/lib/utils";

const SECTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  User, Cpu, Plug, Brain, Key,
};

export function SettingsSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useAppI18n();
  const { isDirty, draft } = useSystemSettings();

  const currentSection = pathname.split("/").pop() as SettingsSectionId;

  const hiddenSections = draft.review?.hidden_sections ?? [];
  const visibleSections = SETTINGS_SECTIONS.filter((s) => {
    const hiddenSectionIds = hiddenSections.map((h) => STEP_TO_SECTION[h] ?? h);
    return !hiddenSectionIds.includes(s.id);
  });

  const mobileTabs = visibleSections.map((section) => ({
    key: section.id,
    label: t(section.labelKey),
    dirty: isDirty(section.id),
  }));

  return (
    <>
      {/* Desktop sidebar */}
      <nav
        aria-label={t("settings.sections.navigation", { defaultValue: "Settings sections" })}
        className="hidden md:flex w-[200px] shrink-0 flex-col gap-0.5 border-r border-[var(--divider-hair)] px-2 py-4"
      >
        {visibleSections.map((section) => {
          const Icon = SECTION_ICONS[section.icon];
          const isActive = currentSection === section.id;
          const hasDirty = isDirty(section.id);

          return (
            <Link
              key={section.id}
              href={`/control-plane/system/${section.id}`}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "group relative flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-3 py-2",
                "text-[0.8125rem] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                isActive
                  ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                  : "text-[var(--text-tertiary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]",
              )}
            >
              {isActive ? (
                <span
                  aria-hidden
                  className="absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-[var(--accent)]"
                />
              ) : null}
              {Icon ? (
                <Icon
                  className={cn(
                    "h-3.5 w-3.5 shrink-0",
                    isActive
                      ? "text-[var(--text-primary)]"
                      : "text-[var(--text-quaternary)] transition-colors group-hover:text-[var(--text-secondary)]",
                  )}
                />
              ) : null}
              <span className="truncate">{t(section.labelKey)}</span>
              {hasDirty ? (
                <span
                  className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]"
                  aria-hidden
                />
              ) : null}
            </Link>
          );
        })}
        <SettingsWarningIndicator className="mt-auto" />
      </nav>

      {/* Mobile tabs */}
      <div className="flex md:hidden items-center gap-2 border-b border-[var(--divider-hair)] px-3 py-2 overflow-x-auto">
        <div className="min-w-0 flex-1">
          <TabBar
            tabs={mobileTabs}
            activeTab={currentSection}
            onTabChange={(key) => router.push(`/control-plane/system/${key}`)}
          />
        </div>
        <SettingsWarningIndicator compact className="shrink-0" />
      </div>
    </>
  );
}
