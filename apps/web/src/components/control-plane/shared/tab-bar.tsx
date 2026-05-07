"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface Tab {
  key: string;
  label: string;
  dirty?: boolean;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (key: string) => void;
}

export function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  const { tl } = useAppI18n();

  return (
    <div
      className="segmented-control segmented-control--single-row"
      role="tablist"
    >
      {tabs.map((tab) => {
        const isActive = tab.key === activeTab;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onTabChange(tab.key)}
            className={cn(
              "segmented-control__option",
              isActive && "is-active",
            )}
            title={tab.dirty ? tl("Alteracoes nao salvas") : undefined}
          >
            <span>{tl(tab.label)}</span>
            {tab.dirty && (
              <span
                className="inline-block h-1.5 w-1.5 rounded-full shrink-0 animate-pulse"
                style={{ backgroundColor: "var(--tone-warning-dot)" }}
                role="status"
                aria-label={tl("Alteracoes nao salvas")}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
