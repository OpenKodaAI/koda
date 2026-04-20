"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Settings } from "lucide-react";
import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  renderIntegrationLogo,
  getIntegrationAccent,
} from "@/components/control-plane/system/integrations/integration-logos";
import {
  ToolGroupSection,
  type ToolItem,
  type GroupPolicy,
} from "@/components/control-plane/shared/tool-group-section";
import {
  CompactGrantToggle,
  type CompactGrantOption,
} from "@/components/control-plane/shared/compact-grant-toggle";
import type { ToolPolicy } from "@/components/control-plane/shared/tool-policy-segment";
import type {
  AgentIntegrationEntry,
  IntegrationGrantValue,
} from "@/hooks/use-agent-integration-permissions";
import type { McpOAuthStatus } from "@/lib/control-plane";
import { INTEGRATION_CATALOG } from "@/components/control-plane/system/integrations/integration-catalog-data";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  GrantSwitch (compact animated toggle)                              */
/* ------------------------------------------------------------------ */

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
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200"
      style={{
        backgroundColor: checked
          ? "var(--tone-success-bg-strong)"
          : "var(--field-bg)",
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
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type IntegrationPermissionDetailProps = {
  entry: AgentIntegrationEntry;
  onBack: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onGrantConfigChange?: (patch: Partial<IntegrationGrantValue>) => void;
  onConnectCore?: () => void;
  onImportDefault?: () => void;
  onDisconnectCore?: () => void;
  canImportDefault?: boolean;
  onConnectOAuth?: () => void;
  onConnectManual?: () => void;
  oauthSupported?: boolean;
  oauthStatus?: McpOAuthStatus;
  isOAuthLoading?: boolean;
  onDisconnect?: () => void;
  onToolPolicyChange: (toolId: string, policy: ToolPolicy) => void;
  onGroupPolicyChange: (group: string, policy: ToolPolicy) => void;
  onDiscoverTools?: () => void;
  isDiscovering?: boolean;
  sharedEnvOptions?: CompactGrantOption[];
  secretOptions?: CompactGrantOption[];
};

/* ------------------------------------------------------------------ */
/*  Helpers: build tool items from MCP / core data                     */
/* ------------------------------------------------------------------ */

function buildMcpToolItems(
  entry: AgentIntegrationEntry,
): { readOnly: ToolItem[]; interactive: ToolItem[] } {
  const tools = entry.mcpTools ?? [];
  const policies = entry.mcpPolicies ?? {};

  const readOnly: ToolItem[] = [];
  const interactive: ToolItem[] = [];

  for (const tool of tools) {
    const item: ToolItem = {
      id: tool.name,
      label: tool.annotations?.title || tool.name,
      description: tool.description,
      policy: (policies[tool.name] as ToolPolicy) || "always_ask",
    };

    if (tool.annotations?.read_only_hint === true) {
      readOnly.push(item);
    } else {
      interactive.push(item);
    }
  }

  return { readOnly, interactive };
}

function buildCoreToolItems(entry: AgentIntegrationEntry): ToolItem[] {
  const catalogEntry = INTEGRATION_CATALOG.find(
    (e) => e.key === entry.key,
  );
  if (!catalogEntry) return [];

  const grant = entry.coreGrant;
  const allowSet = new Set(grant?.allow_actions ?? []);
  const denySet = new Set(grant?.deny_actions ?? []);

  return catalogEntry.capabilities.map((cap) => {
    let policy: ToolPolicy = "always_ask";
    if (denySet.has(cap.id) || denySet.has(cap.label)) {
      policy = "blocked";
    } else if (
      allowSet.size > 0 &&
      (allowSet.has(cap.id) || allowSet.has(cap.label))
    ) {
      policy = "always_allow";
    } else if (allowSet.size === 0 && denySet.size === 0 && grant?.enabled) {
      // All allowed by default when no explicit allow/deny lists
      policy = "always_allow";
    }
    return {
      id: cap.id,
      label: cap.label,
      description: cap.description,
      policy,
    };
  });
}

function computeGroupPolicy(tools: ToolItem[]): GroupPolicy {
  if (tools.length === 0) return "always_ask";
  const first = tools[0].policy;
  const unanimous = tools.every((t) => t.policy === first);
  return unanimous ? first : "custom";
}

function parseConstraintList(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function describeCoreSourceOrigin(
  value: string | null | undefined,
  tl: (text: string, vars?: Record<string, string | number>) => string,
) {
  if (value === "imported_default") return tl("Padrão importado do sistema");
  if (value === "local_session") return tl("Sessão local desta máquina");
  if (value === "system_default") return tl("Padrão do sistema");
  return tl("Binding próprio do agente");
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function IntegrationPermissionDetail({
  entry,
  onBack,
  onToggleEnabled,
  onGrantConfigChange,
  onConnectCore,
  onImportDefault,
  onDisconnectCore,
  canImportDefault = false,
  onConnectOAuth,
  onConnectManual,
  oauthSupported,
  oauthStatus,
  isOAuthLoading,
  onDisconnect,
  onToolPolicyChange,
  onGroupPolicyChange,
  onDiscoverTools,
  isDiscovering = false,
  sharedEnvOptions = [],
  secretOptions = [],
}: IntegrationPermissionDetailProps) {
  const { tl } = useAppI18n();
  const accent = getIntegrationAccent(entry.logoKey);
  const [evaluatedAt, setEvaluatedAt] = useState(() => Date.now());
  const coreGrant = entry.kind === "core" ? entry.coreGrant ?? {} : null;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setEvaluatedAt(Date.now());
    }, 0);
    return () => window.clearTimeout(timer);
  }, [oauthStatus?.expires_at]);

  const isTokenExpiring = oauthStatus?.expires_at
    ? new Date(oauthStatus.expires_at).getTime() - evaluatedAt < 24 * 60 * 60 * 1000
    : false;
  const coreConnection = entry.kind === "core" ? entry.coreConnection ?? null : null;
  const coreDefaultConnection = entry.kind === "core" ? entry.coreDefaultConnection ?? null : null;

  /* ---- MCP tool groups ------------------------------------------- */
  const mcpGroups = useMemo(() => {
    if (entry.kind !== "mcp") return null;
    return buildMcpToolItems(entry);
  }, [entry]);

  /* ---- Core capability items ------------------------------------- */
  const coreTools = useMemo(() => {
    if (entry.kind !== "core") return null;
    return buildCoreToolItems(entry);
  }, [entry]);

  const hasMcpTools =
    mcpGroups !== null &&
    (mcpGroups.readOnly.length > 0 || mcpGroups.interactive.length > 0);

  const hasCoreCapabilities =
    coreTools !== null && coreTools.length > 0;

  function updateGrantPatch(patch: Partial<IntegrationGrantValue>) {
    onGrantConfigChange?.(patch);
  }

  function toggleGrantListValue(field: "shared_env_keys" | "secret_keys", value: string) {
    if (!coreGrant) return;
    const current = coreGrant[field] ?? [];
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    updateGrantPatch({ [field]: next } as Partial<IntegrationGrantValue>);
  }

  /* ---- Render ---------------------------------------------------- */
  return (
    <div className="flex flex-col gap-4">
      {/* 1. Breadcrumb */}
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        <ArrowLeft size={16} />
        <span>
          {tl("Integracoes")}
          <span className="mx-1 text-[var(--text-quaternary)]">/</span>
          <span className="text-[var(--text-primary)]">{entry.label}</span>
        </span>
      </button>

      {/* 2. Header */}
      <div className="flex items-center gap-4">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-xl"
          style={{ backgroundColor: `${accent.from}18` }}
        >
          {renderIntegrationLogo(entry.logoKey, "h-6 w-6")}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-[var(--text-primary)]">
              {entry.label}
            </span>
            <span className="rounded-md border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-quaternary)]">
              {entry.kind === "mcp" ? "MCP" : tl("Core")}
            </span>
          </div>
        </div>

        {/* Toggle / Disconnect */}
        {entry.kind === "core" ? (
          <GrantSwitch
            checked={entry.coreGrant?.enabled === true}
            onChange={onToggleEnabled}
          />
        ) : entry.mcpConnection ? (
          <button
            type="button"
            onClick={onDisconnect}
            className="rounded-xl border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--border-strong)] transition-colors"
          >
            {tl("Desconectar")}
          </button>
        ) : null}
      </div>

      {/* 3. Description */}
      {entry.description && (
        <p className="text-sm leading-relaxed text-[var(--text-tertiary)]">
          {entry.description}
        </p>
      )}

      {/* 3b. OAuth connection status */}
      {entry.mcpConnection && oauthStatus?.auth_method === "oauth" && (
        <div className="flex items-center gap-2 rounded-lg bg-[rgba(113,219,190,0.06)] px-3 py-2 text-xs">
          <span
            className="h-2 w-2 rounded-full"
            style={{
              backgroundColor: oauthStatus.connected && !isTokenExpiring
                ? "var(--tone-success-dot)"
                : isTokenExpiring
                  ? "var(--tone-warning-dot)"
                  : "var(--tone-danger-dot)",
            }}
          />
          <span className="text-[var(--text-secondary)]">
            {oauthStatus.account_label || tl("OAuth conectado")}
          </span>
          {isTokenExpiring && (
            <button
              type="button"
              onClick={onConnectOAuth}
              className="ml-auto text-[10px] font-medium text-[var(--tone-warning-text)] underline"
            >
              {tl("Reconectar")}
            </button>
          )}
        </div>
      )}

      {entry.kind === "mcp" && entry.mcpConnection && (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--text-tertiary)]">
            <span>
              {tl("Tools")}: {entry.mcpSummary?.total ?? entry.mcpTools?.length ?? 0}
            </span>
            {entry.mcpLastDiscoveredAt && (
              <span>
                {tl("Ultima discovery")}: {new Date(entry.mcpLastDiscoveredAt).toLocaleString()}
              </span>
            )}
            {entry.mcpDiff && (
              <span>
                {tl("Diff")}: +{entry.mcpDiff.added.length} / ~{entry.mcpDiff.changed.length} / -{entry.mcpDiff.removed.length}
              </span>
            )}
          </div>
        </div>
      )}

      {entry.kind === "core" && (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="space-y-1">
              <div className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
                {tl("Conexão do agente")}
              </div>
              <div className="text-sm text-[var(--text-secondary)]">
                {coreConnection?.connected
                  ? tl("Este agente já possui um binding próprio para essa integração.")
                  : tl("Sem binding ativo. O agente não usa credenciais implícitas do host.")}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {canImportDefault ? (
                <button
                  type="button"
                  onClick={onImportDefault}
                  className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                >
                  {tl("Importar padrão")}
                </button>
              ) : null}
              {onConnectCore ? (
                <button
                  type="button"
                  onClick={onConnectCore}
                  className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                >
                  {coreConnection?.connected ? tl("Editar conexão") : tl("Conectar")}
                </button>
              ) : null}
              {coreConnection?.connected && onDisconnectCore ? (
                <button
                  type="button"
                  onClick={onDisconnectCore}
                  className="rounded-lg border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-3 py-1.5 text-xs font-medium text-[var(--tone-danger-text)] transition-colors hover:bg-[var(--tone-danger-bg-strong)]"
                >
                  {tl("Desconectar")}
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-[var(--text-tertiary)]">
            <span>
              {tl("Origem")}: {coreConnection?.connected ? describeCoreSourceOrigin(coreConnection?.source_origin, tl) : tl("Sem binding ativo")}
            </span>
            {coreConnection?.auth_method ? (
              <span>
                {tl("Auth")}: {coreConnection.auth_method}
              </span>
            ) : null}
            {coreConnection?.account_label ? (
              <span>
                {tl("Conta")}: {coreConnection.account_label}
              </span>
            ) : null}
            {coreConnection?.last_verified_at ? (
              <span>
                {tl("Última verificação")}: {new Date(coreConnection.last_verified_at).toLocaleString()}
              </span>
            ) : null}
            {coreConnection?.expires_at ? (
              <span>
                {tl("Expira em")}: {new Date(coreConnection.expires_at).toLocaleString()}
              </span>
            ) : null}
          </div>

          {!coreConnection?.connected && coreDefaultConnection?.connected ? (
            <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {tl("Existe um padrão do sistema disponível para importar com auth {{auth}}.", {
                auth: coreDefaultConnection.auth_method || tl("manual"),
              })}
            </div>
          ) : null}

          {coreConnection?.last_error ? (
            <div className="mt-3 rounded-lg border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-xs text-[var(--tone-warning-text)]">
              {coreConnection.last_error}
            </div>
          ) : null}
        </div>
      )}

      {/* 4. Tool permissions header */}
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{tl("Permissoes de ferramentas")}</span>
        <span className="text-xs text-[var(--text-quaternary)]">
          {tl("Escolha quando o agente pode executar cada ferramenta.")}
        </span>
      </div>

      {entry.kind === "core" && coreGrant && onGrantConfigChange ? (
        <div className="flex flex-col gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">{tl("Restricoes de runtime")}</span>
            <span className="text-xs text-[var(--text-quaternary)]">
              {tl("Esses limites tambem entram na decisao central de policy em runtime.")}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {tl("Allowed domains")}
              </span>
              <input
                type="text"
                value={(coreGrant.allowed_domains ?? []).join(", ")}
                onChange={(event) =>
                  updateGrantPatch({ allowed_domains: parseConstraintList(event.target.value) })
                }
                placeholder="googleapis.com, api.github.com"
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {tl("Allowed paths")}
              </span>
              <input
                type="text"
                value={(coreGrant.allowed_paths ?? []).join(", ")}
                onChange={(event) =>
                  updateGrantPatch({ allowed_paths: parseConstraintList(event.target.value) })
                }
                placeholder="/workspace/project, /tmp/reports"
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {tl("Allowed DB envs")}
              </span>
              <input
                type="text"
                value={(coreGrant.allowed_db_envs ?? []).join(", ")}
                onChange={(event) =>
                  updateGrantPatch({ allowed_db_envs: parseConstraintList(event.target.value) })
                }
                placeholder="dev, staging, readonly"
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  {tl("Allow private network")}
                </span>
                <span className="text-[11px] text-[var(--text-quaternary)]">
                  {tl("Necessario para destinos internos, localhost e IPs privados.")}
                </span>
              </div>
              <GrantSwitch
                checked={coreGrant.allow_private_network === true}
                onChange={(checked) => updateGrantPatch({ allow_private_network: checked })}
              />
            </div>
          </div>

          {(sharedEnvOptions.length > 0 || secretOptions.length > 0) ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CompactGrantToggle
                title={tl("Shared env por integracao")}
                description={tl("Disponivel apenas para execucoes desta integracao.")}
                options={sharedEnvOptions}
                selected={coreGrant.shared_env_keys ?? []}
                onToggle={(value) => toggleGrantListValue("shared_env_keys", value)}
              />
              <CompactGrantToggle
                title={tl("Secrets por integracao")}
                description={tl("Reduz a exposicao sensivel ao escopo minimo necessario.")}
                options={secretOptions}
                selected={coreGrant.secret_keys ?? []}
                onToggle={(value) => toggleGrantListValue("secret_keys", value)}
              />
            </div>
          ) : null}
        </div>
      ) : null}

      {/* 5. Tool groups — MCP */}
      {entry.kind === "mcp" && (
        <>
          {/* Discovering state */}
          {isDiscovering && (
            <div className="flex items-center gap-2 py-6 justify-center">
              <Loader2
                size={16}
                className="animate-spin text-[var(--text-tertiary)]"
              />
              <span className="text-sm text-[var(--text-tertiary)]">
                {tl("Descobrindo ferramentas...")}
              </span>
            </div>
          )}

          {/* No tools state */}
          {!isDiscovering && !hasMcpTools && entry.mcpConnection && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center">
              <p className="text-sm text-[var(--text-quaternary)]">
                {tl("Nenhuma ferramenta descoberta")}
              </p>
              {onDiscoverTools && (
                <button
                  type="button"
                  onClick={onDiscoverTools}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)]",
                    "px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)]",
                    "transition-colors hover:bg-[var(--surface-hover)]",
                  )}
                >
                  <RefreshCw size={12} />
                  {tl("Descobrir ferramentas")}
                </button>
              )}
            </div>
          )}

          {/* Not connected — show connect options */}
          {!isDiscovering && !entry.mcpConnection && (
            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 flex flex-col items-center gap-3">
              <p className="text-sm text-[var(--text-quaternary)]">
                {tl("Conecte para descobrir e gerenciar ferramentas.")}
              </p>
              <div className="flex items-center gap-2">
                {/* Primary: OAuth button (if supported) */}
                {oauthSupported && onConnectOAuth && (
                  <button
                    type="button"
                    onClick={onConnectOAuth}
                    disabled={isOAuthLoading}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-xl",
                      "bg-[var(--surface-elevated)] border border-[var(--border-strong)]",
                      "px-4 py-2 text-sm font-medium text-[var(--text-primary)]",
                      "transition-all hover:bg-[var(--surface-hover-strong)]",
                      isOAuthLoading && "opacity-60 cursor-wait",
                    )}
                  >
                    {isOAuthLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : null}
                    {tl("Conectar com {{provider}}", { provider: entry.label })}
                  </button>
                )}

                {/* Secondary: Manual config (gear icon or text button) */}
                {onConnectManual && (
                  oauthSupported ? (
                    /* Gear icon when OAuth is primary */
                    <button
                      type="button"
                      onClick={onConnectManual}
                      title={tl("Configuracao manual")}
                      className={cn(
                        "inline-flex items-center justify-center rounded-xl",
                        "border border-[var(--border-subtle)] bg-transparent",
                        "h-9 w-9 text-[var(--text-tertiary)]",
                        "transition-all hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)]",
                      )}
                    >
                      <Settings size={16} />
                    </button>
                  ) : (
                    /* Full button when no OAuth available */
                    <button
                      type="button"
                      onClick={onConnectManual}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-xl",
                        "border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]",
                        "px-4 py-2 text-sm font-medium text-[var(--text-primary)]",
                        "transition-all hover:border-[var(--border-strong)]",
                      )}
                    >
                      {tl("Configurar conexao")}
                    </button>
                  )
                )}
              </div>
            </div>
          )}

          {/* Tool groups rendered */}
          {!isDiscovering && hasMcpTools && mcpGroups && (
            <div className="flex flex-col gap-2">
              {mcpGroups.readOnly.length > 0 && (
                <ToolGroupSection
                  label="Ferramentas somente leitura"
                  count={mcpGroups.readOnly.length}
                  tools={mcpGroups.readOnly}
                  groupPolicy={computeGroupPolicy(mcpGroups.readOnly)}
                  onGroupPolicyChange={(policy) =>
                    onGroupPolicyChange("read_only", policy)
                  }
                  onToolPolicyChange={onToolPolicyChange}
                  defaultExpanded
                />
              )}
              {mcpGroups.interactive.length > 0 && (
                <ToolGroupSection
                  label="Ferramentas interativas"
                  count={mcpGroups.interactive.length}
                  tools={mcpGroups.interactive}
                  groupPolicy={computeGroupPolicy(mcpGroups.interactive)}
                  onGroupPolicyChange={(policy) =>
                    onGroupPolicyChange("interactive", policy)
                  }
                  onToolPolicyChange={onToolPolicyChange}
                  defaultExpanded
                />
              )}
            </div>
          )}
        </>
      )}

      {/* 5. Tool groups — Core */}
      {entry.kind === "core" && (
        <>
          {hasCoreCapabilities && coreTools ? (
            <ToolGroupSection
              label="Capacidades"
              count={coreTools.length}
              tools={coreTools}
              groupPolicy={computeGroupPolicy(coreTools)}
              onGroupPolicyChange={(policy) =>
                onGroupPolicyChange("capabilities", policy)
              }
              onToolPolicyChange={onToolPolicyChange}
              defaultExpanded
            />
          ) : (
            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center">
              <p className="text-sm text-[var(--text-quaternary)]">
                {entry.coreGrant?.enabled
                  ? tl("Integracao habilitada. Sem capacidades granulares configuradas.")
                  : tl("Integracao desabilitada.")}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
