"use client";

import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { findFieldError } from "@/lib/system-settings-schema";
import type { GeneralSystemSettings } from "@/lib/control-plane";

type SchedulerValues = GeneralSystemSettings["values"]["scheduler"];

function numberOrEmpty(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function parseIntOrNull(raw: string): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  return Math.trunc(parsed);
}

function parseFloatOrNull(raw: string): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

export function SectionScheduler() {
  const { draft, setField, sectionErrors } = useSystemSettings();
  const { tl } = useAppI18n();
  const scheduler = draft.values.scheduler;
  const errors = sectionErrors.scheduler;

  function update(patch: Partial<SchedulerValues>) {
    setField("scheduler", { ...scheduler, ...patch });
  }

  return (
    <SettingsSectionShell
      sectionId="scheduler"
      title="settings.sections.scheduler.label"
      description="settings.sections.scheduler.description"
    >
      <SettingsFieldGroup title={tl("Agendador")}>
        <ToggleField
          label={tl("Agendador ativo")}
          description={tl("Liga o loop de execução de agendamentos e retries.")}
          checked={scheduler.scheduler_enabled}
          onChange={(next) => update({ scheduler_enabled: next })}
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={tl("Intervalo de polling (s)")}
            description={tl("Frequência de verificação do agendador por novas tarefas.")}
            error={findFieldError(errors, "scheduler.scheduler_poll_interval_seconds")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_poll_interval_seconds)}
              placeholder="5"
              onChange={(e) =>
                update({ scheduler_poll_interval_seconds: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Lease (s)")}
            description={tl("Duração do lock de lease por agendamento em execução.")}
            error={findFieldError(errors, "scheduler.scheduler_lease_seconds")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_lease_seconds)}
              placeholder="60"
              onChange={(e) =>
                update({ scheduler_lease_seconds: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Tentativas máximas por execução")}
            description={tl("Número de retries antes de marcar falha.")}
            error={findFieldError(errors, "scheduler.scheduler_run_max_attempts")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_run_max_attempts)}
              placeholder="3"
              onChange={(e) =>
                update({ scheduler_run_max_attempts: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Intervalo mínimo (s)")}
            description={tl("Intervalo mínimo permitido entre execuções agendadas.")}
            error={findFieldError(errors, "scheduler.scheduler_min_interval_seconds")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_min_interval_seconds)}
              placeholder="60"
              onChange={(e) =>
                update({ scheduler_min_interval_seconds: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Retry base (s)")}
            description={tl("Delay inicial entre tentativas.")}
            error={findFieldError(errors, "scheduler.scheduler_retry_base_delay")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_retry_base_delay)}
              placeholder="30"
              onChange={(e) =>
                update({ scheduler_retry_base_delay: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Retry máximo (s)")}
            description={tl("Delay máximo após backoff exponencial.")}
            error={findFieldError(errors, "scheduler.scheduler_retry_max_delay")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.scheduler_retry_max_delay)}
              placeholder="3600"
              onChange={(e) =>
                update({ scheduler_retry_max_delay: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>
        </div>
      </SettingsFieldGroup>

      <SettingsFieldGroup title={tl("Runbook Governance")}>
        <ToggleField
          label={tl("Governança de runbooks")}
          description={tl("Habilita o sweep diário que revalida runbooks publicados.")}
          checked={scheduler.runbook_governance_enabled}
          onChange={(next) => update({ runbook_governance_enabled: next })}
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={tl("Hora do sweep (0-23)")}
            description={tl("Hora local do dia em que a governança roda.")}
            error={findFieldError(errors, "scheduler.runbook_governance_hour")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={0}
              max={23}
              value={numberOrEmpty(scheduler.runbook_governance_hour)}
              placeholder="4"
              onChange={(e) =>
                update({ runbook_governance_hour: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Dias antes de marcar obsoleto")}
            description={tl("Um runbook é considerado stale após este número de dias sem execução.")}
            error={findFieldError(errors, "scheduler.runbook_revalidation_stale_days")?.message}
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.runbook_revalidation_stale_days)}
              placeholder="30"
              onChange={(e) =>
                update({ runbook_revalidation_stale_days: parseIntOrNull(e.target.value) })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Mínimo de execuções verificadas")}
            description={tl("Volume mínimo para revalidar um runbook.")}
            error={
              findFieldError(errors, "scheduler.runbook_revalidation_min_verified_runs")?.message
            }
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.runbook_revalidation_min_verified_runs)}
              placeholder="5"
              onChange={(e) =>
                update({
                  runbook_revalidation_min_verified_runs: parseIntOrNull(e.target.value),
                })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Taxa mínima de sucesso (0-1)")}
            description={tl("Taxa mínima de sucesso exigida para um runbook continuar ativo.")}
            error={
              findFieldError(errors, "scheduler.runbook_revalidation_min_success_rate")?.message
            }
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={numberOrEmpty(scheduler.runbook_revalidation_min_success_rate)}
              placeholder="0.85"
              onChange={(e) =>
                update({
                  runbook_revalidation_min_success_rate: parseFloatOrNull(e.target.value),
                })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Limite de correções")}
            description={tl("Após este número de correções, o runbook é revalidado.")}
            error={
              findFieldError(errors, "scheduler.runbook_revalidation_correction_threshold")
                ?.message
            }
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.runbook_revalidation_correction_threshold)}
              placeholder="3"
              onChange={(e) =>
                update({
                  runbook_revalidation_correction_threshold: parseIntOrNull(e.target.value),
                })
              }
            />
          </FieldShell>

          <FieldShell
            label={tl("Limite de rollbacks")}
            description={tl("Após este número de rollbacks, o runbook é rebaixado.")}
            error={
              findFieldError(errors, "scheduler.runbook_revalidation_rollback_threshold")
                ?.message
            }
          >
            <input
              className="field-shell text-[var(--text-primary)]"
              type="number"
              min={1}
              value={numberOrEmpty(scheduler.runbook_revalidation_rollback_threshold)}
              placeholder="2"
              onChange={(e) =>
                update({
                  runbook_revalidation_rollback_threshold: parseIntOrNull(e.target.value),
                })
              }
            />
          </FieldShell>
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
