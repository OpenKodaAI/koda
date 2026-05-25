"use client";

import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { ProviderGrid } from "@/components/control-plane/system/integrations/provider-grid";
import { translate } from "@/lib/i18n";

export function SectionIntegrations() {
  return (
    <SettingsSectionShell
      sectionId="integrations"
      title={translate("generated.controlPlane.settings_sections_providers_label_0197a657")}
      description={translate("generated.controlPlane.settings_sections_providers_description_5c381708")}
      hideHeader
    >
      <ProviderGrid />
    </SettingsSectionShell>
  );
}
