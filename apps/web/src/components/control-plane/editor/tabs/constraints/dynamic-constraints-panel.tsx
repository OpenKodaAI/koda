"use client";

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
  const { tl } = useAppI18n();
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
        placeholder={placeholder ?? tl("Separe por vírgulas")}
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
  const { tl } = useAppI18n();

  if (!constraints || constraints.length === 0) {
    return null;
  }

  const allowedDomains = (grant.allowed_domains ?? []).join(", ");
  const allowedPaths = (grant.allowed_paths ?? []).join(", ");
  const allowedDbEnvs = (grant.allowed_db_envs ?? []).join(", ");

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4">
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{tl("Restrições de runtime")}</span>
        <span className="text-xs text-[var(--text-quaternary)]">
          {tl("Apenas os limites aplicáveis a esta integração.")}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {constraints.includes("allowed_domains") ? (
          <ListField
            label={tl("Domínios permitidos")}
            value={allowedDomains}
            placeholder="googleapis.com, api.github.com"
            onChange={(next) => onPatch({ allowed_domains: next })}
          />
        ) : null}

        {constraints.includes("allowed_paths") ? (
          <ListField
            label={tl("Paths permitidos")}
            value={allowedPaths}
            placeholder="/workspace/project, /tmp/reports"
            onChange={(next) => onPatch({ allowed_paths: next })}
          />
        ) : null}

        {constraints.includes("allowed_db_envs") ? (
          <ListField
            label={tl("DB envs permitidos")}
            value={allowedDbEnvs}
            placeholder="dev, staging, readonly"
            onChange={(next) => onPatch({ allowed_db_envs: next })}
          />
        ) : null}

        {constraints.includes("allow_private_network") ? (
          <div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {tl("Permitir rede privada")}
              </span>
              <span className="text-[11px] text-[var(--text-quaternary)]">
                {tl("Necessário para destinos internos, localhost e IPs privados.")}
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
                {tl("Modo somente leitura")}
              </span>
              <span className="text-[11px] text-[var(--text-quaternary)]">
                {tl("Bloqueia tools destrutivas no runtime mesmo que a conexão permita.")}
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
