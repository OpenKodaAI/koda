"use client";

import { translate } from "@/lib/i18n";
/**
 * DynamicConstraintsPanel
 *
 * Renders only the runtime-constraint controls that the integration's catalog
 * entry declares. If `allow_private_network` isn't applicable (e.g. Jira),
 * the switch is not in the DOM.
 */

import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  IntegrationGrantValue,
} from "@/hooks/use-agent-integration-permissions";
import type { RuntimeConstraintKey } from "@/lib/control-plane";

function parseConstraintList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function GrantSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={(event) => {
        event.stopPropagation();
        onChange(!checked);
      }}
      className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200"
      style={{
        backgroundColor: checked ? "var(--tone-success-bg-strong)" : "var(--field-bg)",
      }}
    >
      <motion.span
        className="inline-block h-5 w-5 rounded-full bg-[var(--text-primary)] shadow-sm"
        style={{ marginTop: 2 }}
        animate={{ x: checked ? 22 : 2 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}

type FieldProps = {
  label: string;
  description?: string;
  value: string;
  placeholder?: string;
  onChange: (next: string[]) => void;
};

function ListField({ label, description, value, placeholder, onChange }: FieldProps) {
  const { t } = useAppI18n();
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-[var(--text-secondary)]">{label}</span>
      {description ? (
        <span className="text-[11px] text-[var(--text-quaternary)]">{description}</span>
      ) : null}
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(parseConstraintList(event.target.value))}
        placeholder={placeholder ?? t("generated.controlPlane.separe_por_virgulas_e538ef88")}
        className="field-shell text-[var(--text-primary)]"
      />
    </label>
  );
}

export type DynamicConstraintsPanelProps = {
  constraints: RuntimeConstraintKey[];
  grant: IntegrationGrantValue;
  onPatch: (patch: Partial<IntegrationGrantValue>) => void;
};

export function DynamicConstraintsPanel({
  constraints,
  grant,
  onPatch,
}: DynamicConstraintsPanelProps) {
  const { t } = useAppI18n();

  if (!constraints || constraints.length === 0) {
    return null;
  }

  const allowedDomains = (grant.allowed_domains ?? []).join(", ");
  const allowedPaths = (grant.allowed_paths ?? []).join(", ");
  const allowedDbEnvs = (grant.allowed_db_envs ?? []).join(", ");

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4">
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{t("generated.controlPlane.restricoes_de_runtime_3814efcf")}</span>
        <span className="text-xs text-[var(--text-quaternary)]">
          {t("generated.controlPlane.apenas_os_limites_aplicaveis_a_esta_integrac_21b79406")}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {constraints.includes("allowed_domains") ? (
          <ListField
            label={t("generated.controlPlane.dominios_permitidos_af4880d0")}
            value={allowedDomains}
            placeholder={translate("generated.controlPlane.googleapis_com_api_github_com_1ca6d071")}
            onChange={(next) => onPatch({ allowed_domains: next })}
          />
        ) : null}

        {constraints.includes("allowed_paths") ? (
          <ListField
            label={t("generated.controlPlane.paths_permitidos_461b92bf")}
            value={allowedPaths}
            placeholder="/workspace/project, /tmp/reports"
            onChange={(next) => onPatch({ allowed_paths: next })}
          />
        ) : null}

        {constraints.includes("allowed_db_envs") ? (
          <ListField
            label={t("generated.controlPlane.db_envs_permitidos_b0625b1b")}
            value={allowedDbEnvs}
            placeholder={translate("generated.controlPlane.dev_staging_readonly_e4032aa5")}
            onChange={(next) => onPatch({ allowed_db_envs: next })}
          />
        ) : null}

        {constraints.includes("allow_private_network") ? (
          <div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {t("generated.controlPlane.permitir_rede_privada_52d496b0")}
              </span>
              <span className="text-[11px] text-[var(--text-quaternary)]">
                {t("generated.controlPlane.necessario_para_destinos_internos_localhost__efa3ba7f")}
              </span>
            </div>
            <GrantSwitch
              checked={grant.allow_private_network === true}
              onChange={(checked) => onPatch({ allow_private_network: checked })}
            />
          </div>
        ) : null}

        {constraints.includes("read_only_mode") ? (
          <div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {t("generated.controlPlane.modo_somente_leitura_f27e8e0c")}
              </span>
              <span className="text-[11px] text-[var(--text-quaternary)]">
                {t("generated.controlPlane.bloqueia_tools_destrutivas_no_runtime_mesmo__c011874f")}
              </span>
            </div>
            <GrantSwitch
              checked={(grant as { read_only_mode?: boolean }).read_only_mode === true}
              onChange={(checked) =>
                onPatch({
                  ...(grant as Record<string, unknown>),
                  read_only_mode: checked,
                } as Partial<IntegrationGrantValue>)
              }
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
