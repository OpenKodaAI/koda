"use client";

import type { ReactNode } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { EditorSaveBar } from "@/components/control-plane/shared/editor-save-bar";
import type { SettingsSectionId } from "@/lib/system-settings-model";

export function SettingsSectionShell({
  sectionId,
  title,
  description,
  children,
  hideHeader,
}: {
  sectionId: SettingsSectionId;
  title: string;
  description: string;
  children: ReactNode;
  hideHeader?: boolean;
}) {
  const { t, tl } = useAppI18n();
  const { isDirty, discardSection, handleSave, saving, saveStatus } = useSystemSettings();
  const sectionIsDirty = isDirty(sectionId);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-y-auto px-6 lg:px-10">
        <div className="flex flex-col gap-4 pt-6 pb-6 lg:pt-8">
          {!hideHeader ? (
            <header className="flex flex-col gap-1 border-b border-[var(--divider-hair)] pb-4">
              <h2 className="m-0 text-[1.125rem] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
                {t(title)}
              </h2>
              <p className="m-0 max-w-[720px] text-[0.8125rem] leading-[1.55] text-[var(--text-tertiary)]">
                {t(description)}
              </p>
            </header>
          ) : null}

          {children}
        </div>
      </div>

      <EditorSaveBar
        dirty={sectionIsDirty}
        saving={saving}
        changeCount={sectionIsDirty ? 1 : 0}
        onSave={handleSave}
        onDiscard={() => discardSection(sectionId)}
        error={saveStatus === "error" ? tl("Não foi possível salvar") : null}
        className="px-6 lg:px-10"
      />
    </div>
  );
}
