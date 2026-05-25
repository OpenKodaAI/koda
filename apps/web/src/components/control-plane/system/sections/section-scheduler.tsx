"use client";

import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { findFieldError } from "@/lib/system-settings-schema";
import type { GeneralSystemSettings } from "@/lib/control-plane";
import { translate } from "@/lib/i18n";

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
  const { t } = useAppI18n();
  const scheduler = draft.values.scheduler;
  const errors = sectionErrors.scheduler;

  function update(patch: Partial<SchedulerValues>) {
    setField("scheduler", { ...scheduler, ...patch });
  }

  return (
    <SettingsSectionShell
      sectionId="scheduler"
      title={translate("generated.controlPlane.settings_sections_scheduler_label_b769c8ee")}
      description={translate("generated.controlPlane.settings_sections_scheduler_description_7954ccbf")}
    >
      <SettingsFieldGroup title={t("generated.controlPlane.agendador_39de19b0")}>
        <ToggleField
          label={t("generated.controlPlane.agendador_ativo_08b2d151")}
          description={t("generated.controlPlane.liga_o_loop_de_execucao_de_agendamentos_e_re_c108cb9e")}
          checked={scheduler.scheduler_enabled}
          onChange={(next) => update({ scheduler_enabled: next })}
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={t("generated.controlPlane.intervalo_de_polling_s_c5a979e6")}
            description={t("generated.controlPlane.frequencia_de_verificacao_do_agendador_por_n_0214c8c7")}
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
            label={t("generated.controlPlane.lease_s_43900adb")}
            description={t("generated.controlPlane.duracao_do_lock_de_lease_por_agendamento_em__a528d88a")}
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
            label={t("generated.controlPlane.tentativas_maximas_por_execucao_5368f0b2")}
            description={t("generated.controlPlane.numero_de_retries_antes_de_marcar_falha_bf8f2c93")}
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
            label={t("generated.controlPlane.intervalo_minimo_s_5af5e2dc")}
            description={t("generated.controlPlane.intervalo_minimo_permitido_entre_execucoes_a_5bce3012")}
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
            label={t("generated.controlPlane.retry_base_s_432cae36")}
            description={t("generated.controlPlane.delay_inicial_entre_tentativas_fe395f63")}
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
            label={t("generated.controlPlane.retry_maximo_s_13d87f54")}
            description={t("generated.controlPlane.delay_maximo_apos_backoff_exponencial_3c2a4319")}
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

      <SettingsFieldGroup title={t("generated.controlPlane.runbook_governance_7b9db18a")}>
        <ToggleField
          label={t("generated.controlPlane.governanca_de_runbooks_f2e2f5ee")}
          description={t("generated.controlPlane.habilita_o_sweep_diario_que_revalida_runbook_6337b108")}
          checked={scheduler.runbook_governance_enabled}
          onChange={(next) => update({ runbook_governance_enabled: next })}
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <FieldShell
            label={t("generated.controlPlane.hora_do_sweep_0_23_25c7c0dd")}
            description={t("generated.controlPlane.hora_local_do_dia_em_que_a_governanca_roda_8423b709")}
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
            label={t("generated.controlPlane.dias_antes_de_marcar_obsoleto_f2b61e5d")}
            description={t("generated.controlPlane.um_runbook_e_considerado_stale_apos_este_num_53bc07a3")}
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
            label={t("generated.controlPlane.minimo_de_execucoes_verificadas_6c768abc")}
            description={t("generated.controlPlane.volume_minimo_para_revalidar_um_runbook_5b81c6f7")}
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
            label={t("generated.controlPlane.taxa_minima_de_sucesso_0_1_443a6957")}
            description={t("generated.controlPlane.taxa_minima_de_sucesso_exigida_para_um_runbo_d3156a62")}
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
            label={t("generated.controlPlane.limite_de_correcoes_86d2a7a4")}
            description={t("generated.controlPlane.apos_este_numero_de_correcoes_o_runbook_e_re_125696a9")}
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
            label={t("generated.controlPlane.limite_de_rollbacks_6a8d9334")}
            description={t("generated.controlPlane.apos_este_numero_de_rollbacks_o_runbook_e_re_4c3e2f20")}
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
