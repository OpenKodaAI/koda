"use client";

import type { ReactNode } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import type { SettingsSectionId } from "@/lib/system-settings-model";

export function SettingsSectionShell({
  sectionId,
  title,
  description,
  children,
}: {
  sectionId: SettingsSectionId;
  title: string;
  description: string;
  children: ReactNode;
}) {
  const { t, tl } = useAppI18n();
  const { isDirty, discardSection, handleSave, saving } = useSystemSettings();
  const sectionIsDirty = isDirty(sectionId);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-6 lg:px-10">
        <div className="flex flex-col gap-6 pt-6 pb-4 lg:pt-8 lg:pb-6">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {t(title)}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-tertiary)]">
              {t(description)}
            </p>
          </div>

          {children}
        </div>
      </div>

      {/* Fixed save bar at bottom */}
      <div className="shrink-0 flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] bg-[var(--canvas)] px-6 py-3 lg:px-10">
        {sectionIsDirty && (
          <button
            type="button"
            onClick={() => discardSection(sectionId)}
            className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
          >
            {tl("Descartar")}
          </button>
        )}
        <AsyncActionButton
          type="button"
          disabled={!sectionIsDirty}
          loading={saving}
          onClick={handleSave}
        >
          {saving ? tl("Salvando") : tl("Salvar alterações")}
        </AsyncActionButton>
      </div>
    </div>
  );
}
