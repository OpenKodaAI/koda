"use client";

import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { ProviderGrid } from "@/components/control-plane/system/integrations/provider-grid";

export function SectionIntegrations() {
  return (
    <SettingsSectionShell
      sectionId="integrations"
      title="settings.sections.providers.label"
      description="settings.sections.providers.description"
      hideHeader
    >
      <ProviderGrid />
    </SettingsSectionShell>
  );
}
