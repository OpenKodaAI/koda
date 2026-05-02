"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Loader2, RefreshCw } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { ConnectIntegrationModal } from "./integrations/connect-integration-modal";
import {
  getIntegrationAccent,
  renderIntegrationLogo,
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
import { DynamicConstraintsPanel } from "./constraints/dynamic-constraints-panel";
import type { ToolPolicy } from "@/components/control-plane/shared/tool-policy-segment";
import type {
  AgentIntegrationEntry,
  IntegrationGrantValue,
} from "@/hooks/use-agent-integration-permissions";
import type {
  McpCapabilityKind,
  McpCapabilityPolicy,
  McpOAuthStatus,
} from "@/lib/control-plane";
import { INTEGRATION_CATALOG } from "@/components/control-plane/system/integrations/integration-catalog-data";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type IntegrationPermissionDetailProps = {
  entry: AgentIntegrationEntry;
  onBack: () => void;
  onGrantConfigChange?: (patch: Partial<IntegrationGrantValue>) => void;
  onConnectCore?: () => void;
  onImportDefault?: () => void;
  onDisconnectCore?: () => void;
  canImportDefault?: boolean;
  onConnectOAuth?: () => void;
  onConnectManual?: () => void;
  onConnectInline?: (envValues: Record<string, string>) => Promise<void>;
  onConnectViaJson?: (rawJson: string) => Promise<void>;
  oauthSupported?: boolean;
  oauthStatus?: McpOAuthStatus;
  isOAuthLoading?: boolean;
  onDisconnect?: () => void;
  onToolPolicyChange: (toolId: string, policy: ToolPolicy) => void;
  onGroupPolicyChange: (group: string, policy: ToolPolicy) => void;
  onCapabilityPolicyChange?: (
    kind: McpCapabilityKind,
    name: string,
    policy: McpCapabilityPolicy,
    options?: { exposureMode?: "context" | "tool" | "auto" },
  ) => void;
  onRemoveCustomServer?: () => void;
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
): { readOnly: ToolItem[]; interactive: ToolItem[]; destructive: ToolItem[] } {
  const tools = entry.mcpTools ?? [];
  const policies = entry.mcpPolicies ?? {};

  const readOnly: ToolItem[] = [];
  const interactive: ToolItem[] = [];
  const destructive: ToolItem[] = [];

  for (const tool of tools) {
    const item: ToolItem = {
      id: tool.name,
      label: tool.annotations?.title || tool.name,
      description: tool.description,
      policy: (policies[tool.name] as ToolPolicy) || "always_ask",
    };

    if (tool.annotations?.destructive_hint === true) {
      destructive.push(item);
    } else if (tool.annotations?.read_only_hint === true) {
      readOnly.push(item);
    } else {
      interactive.push(item);
    }
  }

  return { readOnly, interactive, destructive };
}

function buildMcpResourceItems(entry: AgentIntegrationEntry): ToolItem[] {
  const resources = entry.mcpResources ?? [];
  const policies = entry.mcpResourcePolicies ?? {};
  return resources.map((resource) => ({
    id: resource.uri,
    label: resource.name || resource.uri,
    description: [resource.description, resource.mime_type].filter(Boolean).join(" · ") || resource.uri,
    policy: (policies[resource.uri] as ToolPolicy) || "always_ask",
  }));
}

function buildMcpPromptItems(entry: AgentIntegrationEntry): ToolItem[] {
  const prompts = entry.mcpPrompts ?? [];
  const policies = entry.mcpPromptPolicies ?? {};
  return prompts.map((prompt) => {
    const argsLabel = prompt.arguments?.length
      ? ` · ${prompt.arguments.length} argumento(s)`
      : "";
    return {
      id: prompt.name,
      label: prompt.name,
      description: (prompt.description || "") + argsLabel,
      policy: (policies[prompt.name] as ToolPolicy) || "always_ask",
    };
  });
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


/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function IntegrationPermissionDetail({
  entry,
  onBack,
  onGrantConfigChange,
  onConnectCore,
  onImportDefault,
  onDisconnectCore,
  canImportDefault = false,
  onConnectOAuth,
  onConnectInline,
  onConnectViaJson,
  oauthSupported,
  oauthStatus,
  isOAuthLoading,
  onDisconnect,
  onToolPolicyChange,
  onGroupPolicyChange,
  onCapabilityPolicyChange,
  onRemoveCustomServer,
  onDiscoverTools,
  isDiscovering = false,
  sharedEnvOptions = [],
  secretOptions = [],
}: IntegrationPermissionDetailProps) {
  const { tl } = useAppI18n();
  const [evaluatedAt, setEvaluatedAt] = useState(() => Date.now());
  const coreGrant = entry.kind === "core" ? entry.coreGrant ?? {} : null;
  const [connectModalOpen, setConnectModalOpen] = useState(false);

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
        <div className="relative">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-xl"
            style={{
              backgroundColor: `${getIntegrationAccent(entry.logoKey).from}1F`,
            }}
          >
            {renderIntegrationLogo(entry.logoKey, "h-6 w-6")}
          </div>
          {/* Connected check — mirrors the listing card's success indicator
              and sits in the bottom-right of the logo block. */}
          {(entry.kind === "mcp" && entry.mcpConnection) ||
          (entry.kind === "core" && entry.coreConnection?.connected) ? (
            <span
              aria-label={tl("Conectado")}
              className="pointer-events-none absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg-strong)] text-[var(--tone-success-text)] shadow-[0_0_0_2px_var(--canvas)]"
            >
              <Check size={12} strokeWidth={2.5} />
            </span>
          ) : null}
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

        {/* Single primary action: Conectar (OAuth or form-submit) / Desconectar */}
        {entry.kind === "mcp" ? (
          entry.mcpConnection ? (
            <button
              type="button"
              onClick={onDisconnect}
              className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
            >
              {tl("Desconectar")}
            </button>
          ) : oauthSupported && onConnectOAuth ? (
            <button
              type="button"
              onClick={onConnectOAuth}
              disabled={isOAuthLoading}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--interactive-active-text)] transition-all disabled:opacity-60"
              style={{
                background:
                  "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                border: "1px solid var(--interactive-active-border)",
              }}
            >
              {isOAuthLoading ? <Loader2 size={11} className="animate-spin" /> : null}
              {tl("Conectar")}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setConnectModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--interactive-active-text)] transition-all"
              style={{
                background:
                  "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                border: "1px solid var(--interactive-active-border)",
              }}
            >
              {tl("Conectar")}
            </button>
          )
        ) : entry.coreConnection?.connected ? (
          <button
            type="button"
            onClick={onDisconnectCore}
            className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]"
          >
            {tl("Desconectar")}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setConnectModalOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--interactive-active-text)] transition-all"
            style={{
              background:
                "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
              border: "1px solid var(--interactive-active-border)",
            }}
          >
            {tl("Conectar")}
          </button>
        )}
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
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--text-tertiary)]">
            <span>
              {entry.mcpCapabilitySummary?.tool_count ?? entry.mcpSummary?.total ?? entry.mcpTools?.length ?? 0} tools
            </span>
            <span>
              {entry.mcpCapabilitySummary?.resource_count ?? entry.mcpResources?.length ?? 0} resources
            </span>
            <span>
              {entry.mcpCapabilitySummary?.prompt_count ?? entry.mcpPrompts?.length ?? 0} prompts
            </span>
            {onDiscoverTools ? (
              <button
                type="button"
                onClick={onDiscoverTools}
                disabled={isDiscovering}
                className="ml-auto inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-60"
              >
                <RefreshCw size={11} className={isDiscovering ? "animate-spin" : ""} />
                {tl("Re-descobrir")}
              </button>
            ) : null}
            {entry.isCustom && onRemoveCustomServer ? (
              <button
                type="button"
                onClick={onRemoveCustomServer}
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2 py-1 text-[11px] text-[var(--tone-danger-text)] transition-colors hover:bg-[var(--tone-danger-bg-strong)]"
              >
                {tl("Remover")}
              </button>
            ) : null}
          </div>
          {entry.mcpDiscoveryError ? (
            <p className="text-[11px] font-medium text-[var(--tone-danger-dot)]">{entry.mcpDiscoveryError}</p>
          ) : null}
        </div>
      )}

      {entry.kind === "core" && (
        <div className="flex flex-col gap-2">
          {coreConnection?.connected ? (
            <>
              <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--text-tertiary)]">
                {coreConnection?.auth_method ? <span>{coreConnection.auth_method}</span> : null}
                {coreConnection?.account_label ? <span>{coreConnection.account_label}</span> : null}
                {coreConnection?.last_verified_at ? (
                  <span>{new Date(coreConnection.last_verified_at).toLocaleString()}</span>
                ) : null}
                {canImportDefault ? (
                  <button
                    type="button"
                    onClick={onImportDefault}
                    className="ml-auto rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    {tl("Importar padrão")}
                  </button>
                ) : null}
                {onConnectCore ? (
                  <button
                    type="button"
                    onClick={onConnectCore}
                    className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    {tl("Editar")}
                  </button>
                ) : null}
              </div>
            </>
          ) : null}

          {!coreConnection?.connected && coreDefaultConnection?.connected ? (
            <p className="text-xs text-[var(--text-tertiary)]">
              {tl("Há um padrão do sistema disponível para importar.")}
            </p>
          ) : null}

          {coreConnection?.last_error ? (
            <p className="text-xs text-[var(--tone-warning-text)]">{coreConnection.last_error}</p>
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

      {coreGrant && onGrantConfigChange ? (
        <>
          <DynamicConstraintsPanel
            constraints={entry.runtimeConstraints ?? []}
            grant={coreGrant}
            onPatch={updateGrantPatch}
          />

          {entry.kind === "core" && (sharedEnvOptions.length > 0 || secretOptions.length > 0) ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CompactGrantToggle
                title={tl("Shared env por integração")}
                description={tl("Disponível apenas para execuções desta integração.")}
                options={sharedEnvOptions}
                selected={coreGrant.shared_env_keys ?? []}
                onToggle={(value) => toggleGrantListValue("shared_env_keys", value)}
              />
              <CompactGrantToggle
                title={tl("Secrets por integração")}
                description={tl("Reduz a exposição sensível ao escopo mínimo necessário.")}
                options={secretOptions}
                selected={coreGrant.secret_keys ?? []}
                onToggle={(value) => toggleGrantListValue("secret_keys", value)}
              />
            </div>
          ) : null}
        </>
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
              {mcpGroups.destructive.length > 0 && (
                <ToolGroupSection
                  label="Ferramentas destrutivas"
                  count={mcpGroups.destructive.length}
                  tools={mcpGroups.destructive}
                  groupPolicy={computeGroupPolicy(mcpGroups.destructive)}
                  onGroupPolicyChange={(policy) =>
                    onGroupPolicyChange("destructive", policy)
                  }
                  onToolPolicyChange={onToolPolicyChange}
                  defaultExpanded
                />
              )}
            </div>
          )}

          {/* Resources */}
          {!isDiscovering && (entry.mcpResources?.length ?? 0) > 0 && (
            <ToolGroupSection
              label="Resources"
              count={entry.mcpResources?.length ?? 0}
              tools={buildMcpResourceItems(entry)}
              groupPolicy={computeGroupPolicy(buildMcpResourceItems(entry))}
              onGroupPolicyChange={(policy) =>
                (entry.mcpResources ?? []).forEach((r) =>
                  onCapabilityPolicyChange?.("resource", r.uri, policy as McpCapabilityPolicy),
                )
              }
              onToolPolicyChange={(uri, policy) =>
                onCapabilityPolicyChange?.("resource", uri, policy as McpCapabilityPolicy)
              }
              defaultExpanded={false}
            />
          )}

          {/* Prompts */}
          {!isDiscovering && (entry.mcpPrompts?.length ?? 0) > 0 && (
            <ToolGroupSection
              label="Prompts"
              count={entry.mcpPrompts?.length ?? 0}
              tools={buildMcpPromptItems(entry)}
              groupPolicy={computeGroupPolicy(buildMcpPromptItems(entry))}
              onGroupPolicyChange={(policy) =>
                (entry.mcpPrompts ?? []).forEach((p) =>
                  onCapabilityPolicyChange?.("prompt", p.name, policy as McpCapabilityPolicy),
                )
              }
              onToolPolicyChange={(name, policy) =>
                onCapabilityPolicyChange?.("prompt", name, policy as McpCapabilityPolicy)
              }
              defaultExpanded={false}
            />
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

      {/* Connect modal — opened by the "Conectar" header button when the
          integration is not yet connected and OAuth is not the path. */}
      {onConnectInline ? (
        <ConnectIntegrationModal
          open={connectModalOpen}
          entry={entry}
          oauthStatus={oauthStatus}
          onSubmitForm={onConnectInline}
          onSubmitJson={onConnectViaJson}
          onClose={() => setConnectModalOpen(false)}
        />
      ) : null}
    </div>
  );
}
