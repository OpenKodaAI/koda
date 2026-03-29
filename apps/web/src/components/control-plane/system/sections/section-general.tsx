"use client";

import { Plus, Trash2 } from "lucide-react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { sourceBadgeLabel, sourceBadgeTone } from "@/lib/system-settings-model";
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
  const { draft, setField } = useSystemSettings();
  const { tl } = useAppI18n();
  const account = draft.values.account;
  const sourceBadges = draft.source_badges ?? {};

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
      <SettingsFieldGroup title={tl("Owner Identity")}>
        <FieldWithBadge badgeKey="account.owner_name" sourceBadges={sourceBadges}>
          <FieldShell label="Responsável principal">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={account.owner_name}
              onChange={(e) => update({ owner_name: e.target.value })}
              placeholder="Ex.: Jane Doe"
              readOnly={isEnvSourced("account.owner_name")}
              title={isEnvSourced("account.owner_name") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>

        <FieldWithBadge badgeKey="account.owner_email" sourceBadges={sourceBadges}>
          <FieldShell label="Email operacional">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              type="email"
              value={account.owner_email}
              onChange={(e) => update({ owner_email: e.target.value })}
              placeholder="Ex.: operacao@empresa.com"
              readOnly={isEnvSourced("account.owner_email")}
              title={isEnvSourced("account.owner_email") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>

        <FieldWithBadge badgeKey="account.owner_github" sourceBadges={sourceBadges}>
          <FieldShell label="Usuário GitHub">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={account.owner_github}
              onChange={(e) => update({ owner_github: e.target.value })}
              placeholder="Ex.: jane-doe"
              readOnly={isEnvSourced("account.owner_github")}
              title={isEnvSourced("account.owner_github") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>
      </SettingsFieldGroup>

      <SettingsFieldGroup title={tl("Workspace")}>
        <FieldWithBadge badgeKey="account.default_work_dir" sourceBadges={sourceBadges}>
          <FieldShell
            label="Diretório padrão de trabalho"
            description="Raiz usada quando o caso não define workspace específico."
          >
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={account.default_work_dir}
              onChange={(e) => update({ default_work_dir: e.target.value })}
              placeholder="Ex.: /workspace/projetos"
              readOnly={isEnvSourced("account.default_work_dir")}
              title={isEnvSourced("account.default_work_dir") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>

        <FieldWithBadge badgeKey="account.project_dirs" sourceBadges={sourceBadges}>
          <FieldShell
            label="Diretórios de projeto"
            description="Workspaces que ficam naturalmente disponíveis para operação."
          >
            <div className="flex flex-col gap-1.5">
              {account.project_dirs.map((dir, index) => (
                <div key={`${dir}-${index}`} className="flex items-center gap-2">
                  <input
                    className="field-shell flex-1 px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    value={dir}
                    onChange={(e) => {
                      const nextDirs = [...account.project_dirs];
                      nextDirs[index] = e.target.value;
                      update({ project_dirs: nextDirs });
                    }}
                    placeholder="Ex.: /workspace/base"
                    readOnly={isEnvSourced("account.project_dirs")}
                    title={isEnvSourced("account.project_dirs") ? "Set via environment variable" : undefined}
                  />
                  {!isEnvSourced("account.project_dirs") && (
                    <button
                      type="button"
                      onClick={() =>
                        update({
                          project_dirs: account.project_dirs.filter((_, i) => i !== index),
                        })
                      }
                      className="rounded-lg border border-[var(--border-subtle)] p-2 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              {!isEnvSourced("account.project_dirs") && (
                <button
                  type="button"
                  onClick={() => update({ project_dirs: [...account.project_dirs, ""] })}
                  className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                >
                  <Plus size={14} />
                  {tl("Adicionar diretório")}
                </button>
              )}
            </div>
          </FieldShell>
        </FieldWithBadge>
      </SettingsFieldGroup>

      <SettingsFieldGroup title={tl("Operations")}>
        <FieldWithBadge badgeKey="account.scheduler_default_timezone" sourceBadges={sourceBadges}>
          <FieldShell
            label="Timezone padrão"
            description="Aplicado aos agendamentos e à operação global do sistema."
          >
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              value={account.scheduler_default_timezone}
              onChange={(e) => update({ scheduler_default_timezone: e.target.value })}
              placeholder="Ex.: America/Sao_Paulo"
              readOnly={isEnvSourced("account.scheduler_default_timezone")}
              title={isEnvSourced("account.scheduler_default_timezone") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>

        <FieldWithBadge badgeKey="account.rate_limit_per_minute" sourceBadges={sourceBadges}>
          <FieldShell label="Limite global por minuto">
            <input
              className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
              type="number"
              min={0}
              value={account.rate_limit_per_minute ?? ""}
              onChange={(e) =>
                update({
                  rate_limit_per_minute: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              placeholder="Ex.: 10"
              readOnly={isEnvSourced("account.rate_limit_per_minute")}
              title={isEnvSourced("account.rate_limit_per_minute") ? "Set via environment variable" : undefined}
            />
          </FieldShell>
        </FieldWithBadge>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
