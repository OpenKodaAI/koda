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
  const { tl } = useAppI18n();
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
            <span className="eyebrow">{tl("Sistema")}</span>
          </div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {tl("Configuracoes globais e governanca")}
          </h2>
          <p className="text-sm text-[var(--text-tertiary)] max-w-3xl">
            {tl("Configure providers, runtime, integracoes, variaveis compartilhadas e o vault global em um unico lugar. Cada agente recebe apenas os grants explicitamente aprovados.")}
          </p>
        </div>

        <Link
          href="/control-plane/system"
          className="button-shell button-shell--primary shrink-0"
        >
          {tl("Abrir configuracoes do sistema")}
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Cpu size={15} />
            {tl("Providers ativos")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{enabledProviders}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {degradedProviders > 0
              ? tl("{{count}} provider(s) com capacidade degradada", { count: degradedProviders })
              : tl("Todos os providers habilitados estao prontos")}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Wrench size={15} />
            {tl("Tools do core")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{availableTools}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {tl("Subsets por agente continuam governados no editor de cada bot")}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <ShieldCheck size={15} />
            {tl("Recursos compartilhados")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
            {systemSettings.shared_variables.length + systemSettings.global_secrets.length}
          </div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {tl("{{variables}} variavel(is) e {{secrets}} segredo(s)", {
              variables: systemSettings.shared_variables.length,
              secrets: systemSettings.global_secrets.length,
            })}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-muted)] p-4">
          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Settings2 size={15} />
            {tl("Integracoes globais")}
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{activeIntegrations}</div>
          <p className="mt-1 text-xs text-[var(--text-quaternary)]">
            {tl("Segredos exigem grant explicito")}: {resourceScope["global_secrets_require_grant"] ? tl("sim") : tl("nao")}
          </p>
        </div>
      </div>
    </section>
  );
}
