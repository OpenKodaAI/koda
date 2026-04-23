"use client";

import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  const { tl } = useAppI18n();
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
      title="settings.sections.general.label"
      description="settings.sections.general.description"
    >
      <SettingsFieldGroup title={tl("Regional")}>
        <FieldWithBadge badgeKey="account.scheduler_default_timezone" sourceBadges={sourceBadges}>
          <FieldShell
            label="Timezone"
            description="Fuso horário aplicado aos agendamentos e à operação global do sistema."
            error={findFieldError(errors, "account.scheduler_default_timezone")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              value={account.scheduler_default_timezone}
              onChange={(e) => update({ scheduler_default_timezone: e.target.value })}
              placeholder="Ex.: America/Sao_Paulo"
              readOnly={isEnvSourced("account.scheduler_default_timezone")}
              title={isEnvSourced("account.scheduler_default_timezone") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>

        <FieldWithBadge badgeKey="account.time_format" sourceBadges={sourceBadges}>
          <FieldShell
            label="Formato de hora"
            description="Define como os horários são exibidos na interface e nos relatórios."
            error={findFieldError(errors, "account.time_format")?.message}
          >
            <Select
              value={(account as Record<string, unknown>).time_format as string ?? "24h"}
              onValueChange={(v) => update({ time_format: v } as Partial<typeof account>)}
              disabled={isEnvSourced("account.time_format")}
            >
              <SelectTrigger

                title={isEnvSourced("account.time_format") ? "Set via environment variable" : undefined}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24h">24 horas (14:30)</SelectItem>
                <SelectItem value="12h">12 horas (2:30 PM)</SelectItem>
              </SelectContent>
            </Select>
          </FieldShell>
        </FieldWithBadge>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
