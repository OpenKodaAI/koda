"use client";

import Link from "next/link";
import { Settings2, ShieldCheck, Wrench, Cpu } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneCoreTools,
  ControlPlaneSystemSettings,
} from "@/lib/control-plane";

function truthyCount(record: Record<string, unknown>) {
  return Object.values(record).filter(Boolean).length;
}

export function SystemSettingsOverviewCard({
  systemSettings,
  coreTools,
  coreProviders,
  corePolicies,
  coreCapabilities,
}: {
  systemSettings: ControlPlaneSystemSettings;
  coreTools: ControlPlaneCoreTools;
  coreProviders: ControlPlaneCoreProviders;
  corePolicies: ControlPlaneCorePolicies;
  coreCapabilities: ControlPlaneCoreCapabilities;
}) {
  const { t } = useAppI18n();
  const enabledProviders = Array.isArray(coreProviders.enabled_providers)
    ? coreProviders.enabled_providers.length
    : Object.values(coreProviders.providers ?? {}).filter((item) => Boolean(item["enabled"])).length;
  const availableTools = (coreTools.items ?? []).filter((item) => Boolean(item["available"])).length;
  const activeIntegrations = truthyCount(systemSettings.integrations);
  const resourceScope = (corePolicies["resource_scope"] ?? {}) as Record<string, unknown>;
  const capabilityStatuses = (coreCapabilities.providers ?? []).map((item) => String(item["status"] || "unknown"));
  const degradedProviders = capabilityStatuses.filter((status) => status !== "ready").length;

  return (
    <section className="glass-card p-6 flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[var(--text-secondary)]">
            <Settings2 size={16} />
            <span className="eyebrow">{t("generated.controlPlane.sistema_f71c42e9")}</span>
          </div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {t("generated.controlPlane.configuracoes_globais_e_governanca_22e0aa54")}
          </h2>
          <p className="text-sm text-[var(--text-tertiary)] max-w-3xl">
            {t("generated.controlPlane.configure_providers_runtime_integracoes_vari_f864162b")}
          </p>
        </div>

        <Link
          href="/control-plane/system"
          className="button-shell button-shell--primary shrink-0"
        >
          {t("generated.controlPlane.abrir_configuracoes_do_sistema_a4123a59")}
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Cpu size={15} />
            {t("generated.controlPlane.providers_ativos_2647acba")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{enabledProviders}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {degradedProviders > 0
              ? t("generated.controlPlane.count_provider_s_com_capacidade_degradada_a9dea732", { count: degradedProviders })
              : t("generated.controlPlane.todos_os_providers_habilitados_estao_prontos_5b74fa68")}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Wrench size={15} />
            {t("generated.controlPlane.tools_do_core_e4b09683")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{availableTools}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {t("generated.controlPlane.subsets_por_agente_continuam_governados_no_e_68cee3d3")}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <ShieldCheck size={15} />
            {t("generated.controlPlane.recursos_compartilhados_06dad0e2")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
            {systemSettings.shared_variables.length + systemSettings.global_secrets.length}
          </div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {t("generated.controlPlane.variables_variavel_is_e_secrets_segredo_s_a2b2f98f", {
              variables: systemSettings.shared_variables.length,
              secrets: systemSettings.global_secrets.length,
            })}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Settings2 size={15} />
            {t("generated.controlPlane.integracoes_globais_bec133d4")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{activeIntegrations}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {t("generated.controlPlane.segredos_exigem_grant_explicito_79c6f7c6")}: {resourceScope["global_secrets_require_grant"] ? t("generated.controlPlane.sim_aac41e19") : t("generated.controlPlane.nao_683eb8d1")}
          </p>
        </div>
      </div>
    </section>
  );
}
