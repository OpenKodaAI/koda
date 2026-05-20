"use client";

import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { translate } from "@/lib/i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { sourceBadgeLabel, sourceBadgeTone } from "@/lib/system-settings-model";
import { findFieldError } from "@/lib/system-settings-schema";
import type { GeneralSystemSettingsValueSource } from "@/lib/control-plane";

function SourceBadge({ source }: { source: GeneralSystemSettingsValueSource }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${sourceBadgeTone(source)}`}
    >
      {sourceBadgeLabel(source)}
    </span>
  );
}

function FieldWithBadge({
  badgeKey,
  sourceBadges,
  children,
}: {
  badgeKey: string;
  sourceBadges: Record<string, GeneralSystemSettingsValueSource>;
  children: React.ReactNode;
}) {
  const source = sourceBadges[badgeKey];
  if (!source) return <>{children}</>;

  return (
    <div className="relative">
      <span className="absolute right-1 top-[1.1rem] z-10">
        <SourceBadge source={source} />
      </span>
      {children}
    </div>
  );
}

export function SectionGeneral() {
  const { draft, setField, sectionErrors } = useSystemSettings();
  const { t } = useAppI18n();
  const account = draft.values.account;
  const sourceBadges = draft.source_badges ?? {};
  const errors = sectionErrors.general;

  function update(patch: Partial<typeof account>) {
    setField("account", { ...account, ...patch });
  }

  function isEnvSourced(fieldKey: string) {
    return sourceBadges[fieldKey] === "env";
  }

  return (
    <SettingsSectionShell
      sectionId="general"
      title={translate("generated.controlPlane.settings_sections_general_label_4c4121cf")}
      description={translate("generated.controlPlane.settings_sections_general_description_168fdd40")}
    >
      <SettingsFieldGroup title={t("generated.controlPlane.regional_3e018351")}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FieldWithBadge badgeKey="account.scheduler_default_timezone" sourceBadges={sourceBadges}>
            <FieldShell
              label={t("generated.controlPlane.timezone_e4728822")}
              description={t("generated.controlPlane.fuso_horario_aplicado_aos_agendamentos_e_a_o_df9ad515")}
              error={findFieldError(errors, "account.scheduler_default_timezone")?.message}
            >
              <TimezonePicker
                value={account.scheduler_default_timezone}
                onValueChange={(v) => update({ scheduler_default_timezone: v })}
                disabled={isEnvSourced("account.scheduler_default_timezone")}
                title={
                  isEnvSourced("account.scheduler_default_timezone") ? t("generated.controlPlane.set_via_environment_variable_b237c5c6") : undefined
                }
                placeholder={t("generated.controlPlane.selecionar_fuso_horario_00c644d8")}
                searchPlaceholder={t("generated.controlPlane.buscar_fuso_horario_be06fef7")}
                emptyLabel={t("generated.controlPlane.nenhum_fuso_encontrado_14c89616")}
              />
            </FieldShell>
          </FieldWithBadge>

          <FieldWithBadge badgeKey="account.time_format" sourceBadges={sourceBadges}>
            <FieldShell
              label={t("generated.controlPlane.formato_de_hora_253b138b")}
              description={t("generated.controlPlane.define_como_os_horarios_sao_exibidos_na_inte_31ef59dd")}
              error={findFieldError(errors, "account.time_format")?.message}
            >
              <Select
                value={((account as Record<string, unknown>).time_format as string) ?? "24h"}
                onValueChange={(v) => update({ time_format: v } as Partial<typeof account>)}
                disabled={isEnvSourced("account.time_format")}
              >
                <SelectTrigger
                  title={isEnvSourced("account.time_format") ? t("generated.controlPlane.set_via_environment_variable_b237c5c6") : undefined}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24h">{t("generated.controlPlane.24_horas_14_30_1fa48379")}</SelectItem>
                  <SelectItem value="12h">{t("generated.controlPlane.12_horas_2_30_pm_420c549f")}</SelectItem>
                </SelectContent>
              </Select>
            </FieldShell>
          </FieldWithBadge>
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
