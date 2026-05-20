"use client";

import { useMemo, useState } from "react";
import { FilePlus2, Plug, Plus, Search } from "lucide-react";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { useOAuthPopup } from "@/hooks/use-oauth-popup";
import { Input } from "@/components/ui/input";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import {
  useAgentIntegrationPermissions,
  type AgentIntegrationEntry,
  type IntegrationGrantValue,
} from "@/hooks/use-agent-integration-permissions";
import { ConnectionModalRouter } from "./connection/connection-modal-router";
import { IntegrationPermissionDetail } from "./integration-permission-detail";
import { McpCustomServerModal } from "./integrations/mcp-custom-server-modal";
import {
  integrationCardRootClassName,
  IntegrationCardStatusIndicator,
} from "@/components/control-plane/system/integrations/integration-card-presentation";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";
import { requestJson } from "@/lib/http-client";
import {
  parseResourceAccessPolicy,
  serializeResourceAccessPolicy,
} from "@/lib/policy-serializers";
import { AnimatePresence, motion } from "framer-motion";
import { EASE_OUT } from "@/components/control-plane/shared/motion-constants";
import {
  CATEGORY_LABELS,
} from "@/components/control-plane/system/integrations/integration-catalog-data";

// Core integrations (CLI + REST hybrid runtime) are intentionally hidden
// from the per-agent integrations tab. Every previously-visible core entry
// has an MCP equivalent in the catalog (Atlassian → jira/confluence,
// GitHub MCP → gh, GitLab MCP → glab, etc.), and the MCP path is uniform:
// real OAuth where the platform supports it, no host CLI required, and
// transport, sandbox, capabilities and policies are the same shape across
// every integration. Keeping Core invisible avoids the credential-vs-
// runtime mismatch that produced "X connection is not configured" errors
// after a successful PUT.
const VISIBLE_CORE_KEYS = new Set<string>();

const ALL_CATEGORY_LABELS: Record<string, string> = {
  ...CATEGORY_LABELS,
  general: "Geral",
  development: "Desenvolvimento",
  productivity: "Produtividade",
  data: "Dados",
  cloud: "Cloud",
};

function resolveEntryCategory(entry: AgentIntegrationEntry): string {
  return entry.category || "general";
}

type SecretSummaryLike = {
  scope: string;
  secret_key: string;
  preview: string;
  grantable_to_agents?: boolean;
  grantable_to_bots?: boolean;
};

function isGrantableSecret(secret: SecretSummaryLike) {
  return (secret.grantable_to_agents ?? secret.grantable_to_bots) !== false;
}

export function TabIntegracoes() {
  const {
    state,
    core,
    systemSettings,
    updateAgentSpecField,
  } = useAgentEditor();
  const { showToast } = useToast();
  const { t } = useAppI18n();
  const { runAction } = useAsyncAction();

  const agentId = state.agent.id;
  const resourcePolicy = useMemo(
    () => parseResourceAccessPolicy(state.resourceAccessPolicyJson),
    [state.resourceAccessPolicyJson],
  );

  const integrations = core.integrations?.items ?? [];

  const {
    entries: rawIntegrationEntries,
    loading: integrationsLoading,
    selectedEntry: selectedIntegration,
    selectEntry: selectIntegration,
    discoverCapabilities,
    disconnectMcp,
    updateMcpToolPolicy,
    updateMcpCapabilityPolicy,
    addCustomMcpServer,
    importClaudeDesktopMcp,
    removeCustomMcpServer,
    isDiscovering,
    refreshData: refreshIntegrations,
  } = useAgentIntegrationPermissions({
    agentId: agentId,
    coreIntegrations: integrations,
    integrationGrants: resourcePolicy.integration_grants ?? {},
  });

  const integrationEntries = useMemo(
    () => rawIntegrationEntries.filter((entry) => {
      if (entry.kind === "core") return VISIBLE_CORE_KEYS.has(entry.key);
      return true;
    }),
    [rawIntegrationEntries],
  );

  const [integrationSearch, setIntegrationSearch] = useState("");

  const groupedIntegrations = useMemo(() => {
    const query = integrationSearch.toLowerCase().trim();
    const filtered = query
      ? integrationEntries.filter(
          (e) =>
            e.label.toLowerCase().includes(query) ||
            e.tagline.toLowerCase().includes(query) ||
            e.key.toLowerCase().includes(query),
        )
      : integrationEntries;

    const groups = new Map<string, AgentIntegrationEntry[]>();
    for (const entry of filtered) {
      const cat = resolveEntryCategory(entry);
      const bucket = groups.get(cat) ?? [];
      bucket.push(entry);
      groups.set(cat, bucket);
    }

    const ORDER = ["development", "productivity", "data", "cloud", "general"];
    return ORDER
      .filter((cat) => groups.has(cat))
      .map((cat) => ({
        category: cat,
        label: ALL_CATEGORY_LABELS[cat] ?? cat,
        entries: groups.get(cat)!,
      }));
  }, [integrationEntries, integrationSearch]);

  const [connectingMcpServer, setConnectingMcpServer] = useState<AgentIntegrationEntry | null>(null);
  const [editingCoreConnection, setEditingCoreConnection] = useState<AgentIntegrationEntry | null>(null);
  const [customMcpModalMode, setCustomMcpModalMode] = useState<"form" | "json" | null>(null);
  // Tracks which entry started the in-flight OAuth flow so we can land the
  // user on its detail view as soon as the popup posts back. Cleared on
  // success/error/cancel.
  const [pendingOAuthEntryId, setPendingOAuthEntryId] = useState<string | null>(null);

  const {
    startOAuth,
    isLoading: isOAuthLoading,
  } = useOAuthPopup({
    agentId: agentId,
    onSuccess: async () => {
      await refreshIntegrations();
      // Land the user on the detail view of whichever entry triggered the
      // OAuth flow. Falls back to refreshing the currently selected entry
      // (the legacy behavior when OAuth was started from the detail view).
      const targetId = pendingOAuthEntryId ?? selectedIntegration?.id ?? null;
      setPendingOAuthEntryId(null);
      if (targetId) {
        selectIntegration(null);
        setTimeout(() => selectIntegration(targetId), 150);
      }
    },
    onError: (error) => {
      setPendingOAuthEntryId(null);
      showToast(t("generated.controlPlane.erro_na_conexao_oauth_error_61fd59f4", { error }), "warning");
    },
  });

  const grantableGlobalSecrets = (systemSettings.global_secrets as SecretSummaryLike[]).filter(
    isGrantableSecret,
  );
  const grantedSharedKeys = resourcePolicy.allowed_shared_env_keys;
  const grantedSecretKeys = resourcePolicy.allowed_global_secret_keys;

  const sharedVarOptions = [
    ...systemSettings.shared_variables.map((item) => ({
      value: item.key,
      label: item.key,
      status: t("generated.controlPlane.disponivel_globalmente_da91c50c"),
    })),
    ...grantedSharedKeys
      .filter((key) => !systemSettings.shared_variables.some((item) => item.key === key))
      .map((key) => ({
        value: key,
        label: key,
        status: t("generated.controlPlane.indisponivel_54e299bf"),
      })),
  ];

  const globalSecretOptions = [
    ...grantableGlobalSecrets.map((item) => ({
      value: item.secret_key,
      label: item.secret_key,
      status: t("generated.controlPlane.grantavel_2d9b1b4a"),
    })),
    ...grantedSecretKeys
      .filter((key) => !grantableGlobalSecrets.some((item) => item.secret_key === key))
      .map((key) => {
        const protectedSecret = (systemSettings.global_secrets as SecretSummaryLike[]).find(
          (item) => item.secret_key === key,
        );
        return {
          value: key,
          label: key,
          status:
            protectedSecret && isGrantableSecret(protectedSecret) === false
              ? t("generated.controlPlane.somente_sistema_49d36183")
              : t("generated.controlPlane.indisponivel_54e299bf"),
        };
      }),
  ];

  function updateResourcePolicy(
    patch: Partial<typeof resourcePolicy>,
  ) {
    updateAgentSpecField(
      "resourceAccessPolicyJson",
      serializeResourceAccessPolicy({ ...resourcePolicy, ...patch }),
    );
  }

  function handleIntegrationUpdate(integrationId: string, grant: IntegrationGrantValue) {
    const nextGrants = { ...resourcePolicy.integration_grants };
    nextGrants[integrationId] = {
      ...(nextGrants[integrationId] || {}),
      ...grant,
    };
    updateResourcePolicy({ integration_grants: nextGrants });
  }

  async function verifyConnectionSilently(entry: AgentIntegrationEntry) {
    try {
      await requestJson(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/verify`,
        { method: "POST" },
      );
    } catch {
      // The router already showed save feedback; verify failure is surfaced
      // by the integration status refresh and by the detail view.
    }
  }

  async function importCoreDefault(entry: AgentIntegrationEntry) {
    await runAction(
      `import-core-default:${entry.key}`,
      async () => {
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/import-default`,
          {
            method: "POST",
          },
        );
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}/verify`,
          {
            method: "POST",
          },
        );
        await refreshIntegrations();
      },
      {
        successMessage: t("generated.controlPlane.padrao_do_sistema_importado_para_este_agente_b3719846"),
        errorMessage: t("generated.controlPlane.nao_foi_possivel_importar_o_padrao_do_sistem_f3724970"),
      },
    );
  }

  async function disconnectCoreConnection(entry: AgentIntegrationEntry) {
    await runAction(
      `disconnect-core-connection:${entry.key}`,
      async () => {
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}`,
          {
            method: "DELETE",
          },
        );
        await refreshIntegrations();
      },
      {
        successMessage: t("generated.controlPlane.conexao_do_agente_removida_3fa1a90e"),
        errorMessage: t("generated.controlPlane.nao_foi_possivel_remover_a_conexao_deste_age_9c790c11"),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={t("generated.controlPlane.integracoes_fe756444")}
          icon={Plug}
          dirty={state.dirty.agentSpec}
          defaultOpen
          variant="flat"
        >
          <AnimatePresence mode="wait">
            {selectedIntegration ? (
              <motion.div
                key={`detail:${selectedIntegration.id}`}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.28, ease: EASE_OUT as unknown as [number, number, number, number] }}
              >
                <IntegrationPermissionDetail
                  entry={selectedIntegration}
                  onBack={() => selectIntegration(null)}
                  onGrantConfigChange={(patch) => {
                    if (selectedIntegration.kind !== "core") return;
                    const currentGrant = resourcePolicy.integration_grants?.[selectedIntegration.key] ?? {};
                    handleIntegrationUpdate(selectedIntegration.key, {
                      ...currentGrant,
                      ...patch,
                    });
                  }}
                  onConnectCore={
                    selectedIntegration.kind === "core"
                      ? () => setEditingCoreConnection(selectedIntegration)
                      : undefined
                  }
                  onImportDefault={
                    selectedIntegration.kind === "core" &&
                    selectedIntegration.coreDefaultConnection?.connected
                      ? () => importCoreDefault(selectedIntegration)
                      : undefined
                  }
                  onDisconnectCore={
                    selectedIntegration.kind === "core" &&
                    selectedIntegration.coreConnection?.connected
                      ? () => disconnectCoreConnection(selectedIntegration)
                      : undefined
                  }
                  canImportDefault={Boolean(
                    selectedIntegration.kind === "core" &&
                      selectedIntegration.coreDefaultConnection?.connected &&
                      selectedIntegration.coreConnection?.source_origin !== "imported_default",
                  )}
                  onConnectOAuth={
                    selectedIntegration.oauth_supported
                      ? () => {
                          setPendingOAuthEntryId(selectedIntegration.id);
                          return startOAuth(selectedIntegration.connectionKey);
                        }
                      : undefined
                  }
                  onConnectInline={
                    selectedIntegration.kind === "mcp" && !selectedIntegration.mcpConnection
                      ? async (envValues) => {
                          await requestJson(
                            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(
                              selectedIntegration.connectionKey,
                            )}`,
                            {
                              method: "PUT",
                              body: JSON.stringify({ enabled: true, env_values: envValues }),
                            },
                          );
                          await requestJson(
                            `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(
                              selectedIntegration.connectionKey,
                            )}/capabilities/discover`,
                            { method: "POST" },
                          ).catch(() => null);
                          await refreshIntegrations();
                          // Re-select to surface the freshly-loaded capabilities
                          const sid = selectedIntegration.id;
                          selectIntegration(null);
                          setTimeout(() => selectIntegration(sid), 120);
                        }
                      : selectedIntegration.kind === "core" && !selectedIntegration.coreConnection?.connected
                        ? async (envValues) => {
                            // Core integrations expect a `fields` array on
                            // PUT, not env_values. Convert and also flip the
                            // resource-policy grant on so the agent is
                            // immediately allowed to use it.
                            const fields = Object.entries(envValues).map(([key, value]) => ({
                              key,
                              value,
                              clear: false,
                            }));
                            await requestJson(
                              `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(
                                selectedIntegration.connectionKey,
                              )}`,
                              {
                                method: "PUT",
                                body: JSON.stringify({
                                  auth_method: "api_token",
                                  source_origin: "agent_binding",
                                  allow_local_session: false,
                                  enabled: true,
                                  fields,
                                }),
                              },
                            );
                            // Auto-enable grant so the integration is usable.
                            const nextGrants = {
                              ...resourcePolicy.integration_grants,
                              [selectedIntegration.key]: {
                                ...(resourcePolicy.integration_grants?.[selectedIntegration.key] ?? {}),
                                enabled: true,
                              },
                            };
                            updateResourcePolicy({ integration_grants: nextGrants });
                            await verifyConnectionSilently(selectedIntegration);
                            await refreshIntegrations();
                            const sid = selectedIntegration.id;
                            selectIntegration(null);
                            setTimeout(() => selectIntegration(sid), 120);
                          }
                        : undefined
                  }
                  onConnectViaJson={
                    selectedIntegration.kind === "mcp" && !selectedIntegration.mcpConnection
                      ? async (rawJson) => {
                          let parsed: unknown;
                          try {
                            parsed = JSON.parse(rawJson);
                          } catch {
                            throw new Error(t("generated.controlPlane.json_invalido_18ca930c"));
                          }
                          if (!parsed || typeof parsed !== "object" || !("mcpServers" in (parsed as Record<string, unknown>))) {
                            throw new Error(t("generated.controlPlane.esperado_um_objeto_com_mcpservers_76807978"));
                          }
                          await importClaudeDesktopMcp(parsed as { mcpServers: Record<string, unknown> }, {
                            agentScoped: true,
                          });
                          await refreshIntegrations();
                        }
                      : undefined
                  }
                  oauthSupported={selectedIntegration.oauth_supported}
                  oauthStatus={selectedIntegration.oauthStatus}
                  isOAuthLoading={isOAuthLoading}
                  onDisconnect={selectedIntegration.kind === "mcp" ? () => disconnectMcp(selectedIntegration.key) : undefined}
                  onToolPolicyChange={(toolId, policy) => {
                    if (selectedIntegration.kind === "mcp") {
                      updateMcpToolPolicy(selectedIntegration.key, toolId, policy as "always_allow" | "always_ask" | "blocked");
                    } else {
                      const currentGrant = resourcePolicy.integration_grants?.[selectedIntegration.key] ?? {};
                      const allowActions = new Set(currentGrant.allow_actions ?? []);
                      const denyActions = new Set(currentGrant.deny_actions ?? []);
                      allowActions.delete(toolId);
                      denyActions.delete(toolId);
                      if (policy === "always_allow") allowActions.add(toolId);
                      if (policy === "blocked") denyActions.add(toolId);
                      handleIntegrationUpdate(selectedIntegration.key, {
                        ...currentGrant,
                        allow_actions: [...allowActions],
                        deny_actions: [...denyActions],
                      });
                    }
                  }}
                  onGroupPolicyChange={(group, policy) => {
                    if (selectedIntegration.kind === "mcp" && selectedIntegration.mcpTools) {
                      const tools = selectedIntegration.mcpTools.filter((t) =>
                        group === "read-only" ? t.annotations?.read_only_hint === true : t.annotations?.read_only_hint !== true,
                      );
                      for (const tool of tools) {
                        updateMcpToolPolicy(selectedIntegration.key, tool.name, policy as "always_allow" | "always_ask" | "blocked");
                      }
                    }
                  }}
                  onDiscoverTools={selectedIntegration.kind === "mcp" ? () => discoverCapabilities(selectedIntegration.key) : undefined}
                  onCapabilityPolicyChange={
                    selectedIntegration.kind === "mcp"
                      ? (kind, name, policy, options) =>
                          updateMcpCapabilityPolicy(
                            selectedIntegration.key,
                            kind,
                            name,
                            policy,
                            options,
                          )
                      : undefined
                  }
                  onRemoveCustomServer={
                    selectedIntegration.kind === "mcp" && selectedIntegration.isCustom
                      ? async () => {
                          await removeCustomMcpServer(selectedIntegration.key, {
                            agentScoped: selectedIntegration.customScope === "agent",
                          });
                          showToast(t("generated.controlPlane.servidor_mcp_removido_467623d7"), "success");
                          selectIntegration(null);
                        }
                      : undefined
                  }
                  isDiscovering={isDiscovering}
                  sharedEnvOptions={sharedVarOptions}
                  secretOptions={globalSecretOptions}
                />
              </motion.div>
            ) : (
              <motion.div
                key="grid"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.28, ease: EASE_OUT as unknown as [number, number, number, number] }}
              >
                <p className="text-xs text-[var(--text-quaternary)] mb-3">
                  {t("generated.controlPlane.integracoes_nativas_estao_ativas_por_padrao__8b4de9ac")}
                </p>

                <div className="mb-4 flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]" />
                    <Input
                      type="text"
                      value={integrationSearch}
                      onChange={(e) => setIntegrationSearch(e.target.value)}
                      placeholder={t("generated.controlPlane.buscar_integracoes_bd87b9fd")}
                      className="pl-9"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setCustomMcpModalMode("form")}
                    className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Plus size={13} />
                    <span>{t("generated.controlPlane.adicionar_servidor_5ad219d2")}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setCustomMcpModalMode("json")}
                    className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  >
                    <FilePlus2 size={13} />
                    <span>{t("generated.controlPlane.importar_json_283a7ae7")}</span>
                  </button>
                </div>

                {integrationsLoading && integrationEntries.length === 0 ? (
                  // Skeleton mirrors the real grouped layout (category eyebrow
                  // + 2-col card grid) so there's no jarring jump when data
                  // arrives. Card height matches the integration-card height.
                  <div className="flex flex-col gap-5" aria-hidden>
                    {Array.from({ length: 3 }).map((_, groupIdx) => (
                      <div key={groupIdx}>
                        <span className="mb-2 block h-[10px] w-24 rounded bg-[var(--surface-panel-soft)]" />
                        <div className="grid grid-cols-2 gap-2">
                          {Array.from({ length: 6 }).map((__, idx) => (
                            <div
                              key={idx}
                              className="h-[60px] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] animate-pulse"
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : integrationEntries.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
                    {t("generated.controlPlane.nenhuma_integracao_adicional_disponivel_7df27eb4")}
                  </div>
                ) : groupedIntegrations.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
                    {t("generated.controlPlane.nenhuma_integracao_encontrada_para_esta_busc_6956d0ff")}
                  </div>
                ) : (
                  <div className="flex flex-col gap-5">
                    {groupedIntegrations.map((group) => (
                      <div key={group.category}>
                        <span className="mb-2 block text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                          {group.label}
                        </span>
                        <div className="grid grid-cols-2 gap-2">
                          {group.entries.map((entry, idx) => (
                            <motion.div
                              key={entry.id}
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ delay: idx * 0.03, duration: 0.2 }}
                            >
                              <button
                                type="button"
                                onClick={() => selectIntegration(entry.id)}
                                className={integrationCardRootClassName(
                                  entry.status === "disabled" ? "disconnected" : entry.status === "pending" ? "pending" : "connected",
                                )}
                              >
                                <div
                                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
                                  style={{
                                    backgroundColor: entry.status !== "disabled"
                                      ? `${entry.accentFrom}14`
                                      : "rgba(255,255,255,0.04)",
                                  }}
                                >
                                  {renderIntegrationLogo(entry.logoKey, "h-6 w-6") || (
                                    <Plug size={16} className="text-[var(--text-quaternary)]" />
                                  )}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
                                    {entry.label}
                                  </div>
                                  <div className="mt-0.5 truncate text-xs text-[var(--text-quaternary)]">
                                    {entry.tagline}
                                  </div>
                                </div>
                                <IntegrationCardStatusIndicator
                                  status={entry.status === "disabled" ? "disconnected" : entry.status === "pending" ? "pending" : "connected"}
                                />
                              </button>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </PolicyCard>
      </section>

      {/* Per-integration connection modal (router picks the sub-form) */}
      {connectingMcpServer && connectingMcpServer.kind === "mcp" ? (
        <ConnectionModalRouter
          entry={connectingMcpServer}
          agentId={agentId}
          onClose={() => setConnectingMcpServer(null)}
          onSaved={async () => {
            setConnectingMcpServer(null);
            await refreshIntegrations();
            if (selectedIntegration) {
              selectIntegration(null);
              setTimeout(() => selectIntegration(connectingMcpServer.id), 100);
            }
          }}
          onOAuthStart={
            connectingMcpServer.oauth_supported
              ? async () => {
                  setPendingOAuthEntryId(connectingMcpServer.id);
                  await startOAuth(connectingMcpServer.connectionKey);
                }
              : undefined
          }
          isOAuthLoading={isOAuthLoading}
          oauthStatus={connectingMcpServer.oauthStatus}
        />
      ) : null}

      {/* Custom MCP server modal — Form / JSON paste */}
      <McpCustomServerModal
        open={customMcpModalMode !== null}
        defaultMode={customMcpModalMode ?? "form"}
        onClose={() => setCustomMcpModalMode(null)}
        agentLabel={state.displayName || agentId}
        onSubmitForm={async ({ scope, payload }) => {
          const result = await addCustomMcpServer(payload, { agentScoped: scope === "agent" });
          showToast(t("generated.controlPlane.servidor_mcp_adicionado_66b5c0cd"), "success");
          return result;
        }}
        onSubmitImport={async ({ scope, raw }) => {
          const result = await importClaudeDesktopMcp(raw, { agentScoped: scope === "agent" });
          if (result.errors.length > 0) {
            showToast(
              t("generated.controlPlane.count_servidor_es_com_erro_durante_import_0dba4e69", { count: result.errors.length }),
              "warning",
            );
          } else if (result.created.length || result.updated.length) {
            showToast(
              t("generated.controlPlane.importacao_concluida_count_servidor_es_7173a702", {
                count: result.created.length + result.updated.length,
              }),
              "success",
            );
          }
          return result;
        }}
      />

      {editingCoreConnection && editingCoreConnection.kind === "core" ? (
        <ConnectionModalRouter
          entry={editingCoreConnection}
          agentId={agentId}
          onClose={() => setEditingCoreConnection(null)}
          onSaved={async () => {
            const saved = editingCoreConnection;
            setEditingCoreConnection(null);
            await verifyConnectionSilently(saved);
            await refreshIntegrations();
          }}
        />
      ) : null}
    </div>
  );
}
