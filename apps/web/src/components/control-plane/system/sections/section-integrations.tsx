"use client";

import { useState } from "react";
import {
  BookOpen,
  Check,
  AlertTriangle,
  ChevronDown,
  Cloud,
  Database,
  GitBranch,
  Github,
  Mail,
  Ticket,
  Trash2,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";

/* ------------------------------------------------------------------ */
/*  Switch (track only, no label)                                      */
/* ------------------------------------------------------------------ */

function Switch({
  checked,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  onChange: () => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={onChange}
      className="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200"
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

/* ------------------------------------------------------------------ */
/*  Global tool toggle item                                            */
/* ------------------------------------------------------------------ */

function GlobalToolToggle({ tool }: { tool: Record<string, unknown> }) {
  const { draft, toggleGlobalTool } = useSystemSettings();
  const { tl } = useAppI18n();

  const toolId = String(tool.id);
  const toolTitle = String(tool.title ?? toolId);
  const checked = draft.values.resources.global_tools.includes(toolId);

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)] px-3 py-2.5">
      <span className="text-sm text-[var(--text-primary)]">{tl(toolTitle)}</span>
      <Switch
        checked={checked}
        onChange={() => toggleGlobalTool(toolId)}
        ariaLabel={`${checked ? tl("Desabilitar") : tl("Habilitar")} ${tl(toolTitle)}`}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Integration catalog                                                */
/* ------------------------------------------------------------------ */

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  Ticket,
  BookOpen,
  Mail,
  Database,
  Cloud,
  Github,
  GitBranch,
};

type IntegrationEntry = {
  key: string;
  toggleKey: string;
  label: string;
  description: string;
  icon: string;
  hasCredentials: boolean;
};

const INTEGRATION_CATALOG: IntegrationEntry[] = [
  {
    key: "jira",
    toggleKey: "jira_enabled",
    label: "Jira",
    description: "Busca e operações governadas de issues",
    icon: "Ticket",
    hasCredentials: true,
  },
  {
    key: "confluence",
    toggleKey: "confluence_enabled",
    label: "Confluence",
    description: "Leitura governada de páginas e espaços",
    icon: "BookOpen",
    hasCredentials: true,
  },
  {
    key: "gws",
    toggleKey: "gws_enabled",
    label: "Google Workspace",
    description: "Operações via credencial de serviço",
    icon: "Mail",
    hasCredentials: true,
  },
  {
    key: "postgres",
    toggleKey: "postgres_enabled",
    label: "PostgreSQL",
    description: "Consultas governadas e inspeção de schema",
    icon: "Database",
    hasCredentials: true,
  },
  {
    key: "aws",
    toggleKey: "aws_enabled",
    label: "AWS",
    description: "Operações cloud com perfis e região",
    icon: "Cloud",
    hasCredentials: true,
  },
  {
    key: "gh",
    toggleKey: "gh_enabled",
    label: "GitHub",
    description: "CLI para repos, PRs e issues",
    icon: "Github",
    hasCredentials: false,
  },
  {
    key: "glab",
    toggleKey: "glab_enabled",
    label: "GitLab",
    description: "CLI para repos, MRs e pipelines",
    icon: "GitBranch",
    hasCredentials: false,
  },
];

/* ------------------------------------------------------------------ */
/*  Integration card                                                   */
/* ------------------------------------------------------------------ */

function IntegrationCard({ entry }: { entry: IntegrationEntry }) {
  const { draft, toggleIntegration, setCredentialField } = useSystemSettings();
  const { tl } = useAppI18n();
  const [expanded, setExpanded] = useState(false);

  const enabled = Boolean(draft.values.resources.integrations[entry.toggleKey]);
  const credentials = draft.values.integration_credentials[entry.key];
  const hasCredentialTemplate = entry.hasCredentials && credentials;

  let status: "disabled" | "pending" | "connected" = "disabled";
  if (enabled && hasCredentialTemplate) {
    const missingRequired = credentials.fields.filter(
      (f) => f.required && !(f.value || f.value_present),
    );
    status = missingRequired.length === 0 ? "connected" : "pending";
  } else if (enabled) {
    status = "connected";
  }

  const Icon = ICONS[entry.icon];

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-200",
        status === "connected" && "border-[rgba(113,219,190,0.2)] bg-[rgba(113,219,190,0.025)]",
        status === "pending" && "border-[rgba(255,180,76,0.2)] bg-[rgba(255,180,76,0.025)]",
        status === "disabled" && "border-[var(--border-subtle)]",
      )}
    >
      <div className="flex items-center gap-3 px-4 py-2.5">
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
            enabled
              ? "bg-[rgba(113,219,190,0.1)] text-emerald-300"
              : "bg-[rgba(255,255,255,0.04)] text-[var(--text-quaternary)]",
          )}
        >
          {Icon ? <Icon size={16} /> : null}
        </div>

        <div className="min-w-0 flex-1">
          <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {tl(entry.label)}
          </span>
          <span className="ml-2 text-xs text-[var(--text-quaternary)]">
            {tl(entry.description)}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {status !== "disabled" ? (
            <span
              className={cn(
                "inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none",
                status === "connected" && "bg-[rgba(113,219,190,0.1)] text-emerald-300",
                status === "pending" && "bg-[rgba(255,180,76,0.1)] text-amber-300",
              )}
            >
              {status === "connected" ? <Check size={9} /> : <AlertTriangle size={9} />}
              {status === "connected" ? tl("Conectado") : tl("Pendente")}
            </span>
          ) : null}
          {enabled && hasCredentialTemplate ? (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className={cn(
                "rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)]",
                expanded && "bg-[var(--surface-hover)] text-[var(--text-secondary)]",
              )}
            >
              <motion.div
                animate={{ rotate: expanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown size={14} />
              </motion.div>
            </button>
          ) : null}
          <Switch
            checked={enabled}
            onChange={() => {
              toggleIntegration(entry.toggleKey);
              if (enabled) setExpanded(false);
            }}
            ariaLabel={`${enabled ? tl("Desabilitar") : tl("Habilitar")} ${tl(entry.label)}`}
          />
        </div>
      </div>

      {/* Expandable credentials */}
      <AnimatePresence>
        {expanded && enabled && hasCredentialTemplate ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="border-t border-[rgba(255,255,255,0.05)] px-4 pb-4 pt-3">
              <div className="grid gap-3 xl:grid-cols-2">
                {credentials.fields.map((field) => (
                  <FieldShell
                    key={field.key}
                    label={field.label}
                    description={
                      field.storage === "secret" && field.value_present
                        ? tl("Preencha apenas para substituir.")
                        : field.required
                          ? tl("Obrigatório")
                          : tl("Opcional")
                    }
                  >
                    <div className="space-y-2">
                      {field.storage === "secret" && field.value_present ? (
                        <MaskedSecretPreview preview={field.preview} />
                      ) : null}
                      {field.storage === "secret" ? (
                        <SecretInput
                          value={field.value || ""}
                          onChange={(e) =>
                            setCredentialField(entry.key, field.key, (f) => ({
                              ...f,
                              value: e.target.value,
                              clear: false,
                            }))
                          }
                          placeholder={tl("Digite para substituir")}
                        />
                      ) : (
                        <input
                          className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                          type={field.input_type === "password" ? "password" : "text"}
                          value={field.value || ""}
                          onChange={(e) =>
                            setCredentialField(entry.key, field.key, (f) => ({
                              ...f,
                              value: e.target.value,
                              clear: false,
                            }))
                          }
                          placeholder={tl("Preencha o valor")}
                        />
                      )}
                    </div>
                    {field.storage === "secret" && field.value_present ? (
                      <button
                        type="button"
                        onClick={() =>
                          setCredentialField(entry.key, field.key, (f) => ({
                            ...f,
                            value: "",
                            clear: !f.clear,
                          }))
                        }
                        className={cn(
                          "mt-2 inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                          field.clear
                            ? "border-[rgba(255,110,110,0.3)] bg-[rgba(255,110,110,0.12)] text-[var(--tone-danger-text)]"
                            : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                        )}
                      >
                        <Trash2 size={12} />
                        {field.clear ? tl("Será removido ao salvar") : tl("Remover segredo")}
                      </button>
                    ) : null}
                  </FieldShell>
                ))}
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function SectionIntegrations() {
  const { draft } = useSystemSettings();
  const { tl } = useAppI18n();

  const globalTools = draft.catalogs.global_tools;

  return (
    <SettingsSectionShell
      sectionId="integrations"
      title="settings.sections.integrations.label"
      description="settings.sections.integrations.description"
    >
      {globalTools.length > 0 ? (
        <SettingsFieldGroup title={tl("Global Tools")}>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {globalTools.map((tool) => (
              <GlobalToolToggle key={String(tool.id)} tool={tool} />
            ))}
          </div>
        </SettingsFieldGroup>
      ) : null}

      <SettingsFieldGroup title={tl("External Services")}>
        <div className="grid gap-3 xl:grid-cols-2">
          {INTEGRATION_CATALOG.map((entry) => (
            <IntegrationCard key={entry.key} entry={entry} />
          ))}
        </div>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
