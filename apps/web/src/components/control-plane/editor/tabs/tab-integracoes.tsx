"use client";

import { useMemo, useState } from "react";
import { Plug, Search } from "lucide-react";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { useOAuthPopup } from "@/hooks/use-oauth-popup";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import {
  useAgentIntegrationPermissions,
  type AgentIntegrationEntry,
  type IntegrationGrantValue,
} from "@/hooks/use-agent-integration-permissions";
import { CoreConnectionModal } from "./core-connection-modal";
import { IntegrationPermissionDetail } from "./integration-permission-detail";
import { McpConnectionModal } from "./mcp-connection-modal";
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

const VISIBLE_CORE_KEYS = new Set(["gws", "gh", "glab", "jira", "confluence"]);

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
  const { tl } = useAppI18n();
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
    discoverTools,
    disconnectMcp,
    updateMcpToolPolicy,
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

  const {
    startOAuth,
    isLoading: isOAuthLoading,
  } = useOAuthPopup({
    agentId: agentId,
    onSuccess: async () => {
      await refreshIntegrations();
      if (selectedIntegration) {
        const id = selectedIntegration.id;
        selectIntegration(null);
        setTimeout(() => selectIntegration(id), 150);
      }
    },
    onError: (error) => {
      showToast(tl("Erro na conexao OAuth: {{error}}", { error }), "warning");
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
      status: tl("Disponivel globalmente"),
    })),
    ...grantedSharedKeys
      .filter((key) => !systemSettings.shared_variables.some((item) => item.key === key))
      .map((key) => ({
        value: key,
        label: key,
        status: tl("Indisponivel"),
      })),
  ];

  const globalSecretOptions = [
    ...grantableGlobalSecrets.map((item) => ({
      value: item.secret_key,
      label: item.secret_key,
      status: tl("Grantavel"),
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
              ? tl("Somente sistema")
              : tl("Indisponivel"),
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

  function handleIntegrationToggle(integrationId: string, enabled: boolean) {
    const nextGrants = { ...resourcePolicy.integration_grants };
    if (enabled) {
      nextGrants[integrationId] = {
        ...(nextGrants[integrationId] || {}),
        enabled: true,
      };
    } else {
      if (nextGrants[integrationId]) {
        nextGrants[integrationId] = {
          ...nextGrants[integrationId],
          enabled: false,
        };
      }
    }
    updateResourcePolicy({ integration_grants: nextGrants });
  }

  function handleIntegrationUpdate(integrationId: string, grant: IntegrationGrantValue) {
    const nextGrants = { ...resourcePolicy.integration_grants };
    nextGrants[integrationId] = {
      ...(nextGrants[integrationId] || {}),
      ...grant,
    };
    updateResourcePolicy({ integration_grants: nextGrants });
  }

  async function saveCoreConnection(
    entry: AgentIntegrationEntry,
    payload: {
      auth_method: string;
      source_origin: string;
      allow_local_session: boolean;
      fields: Array<{ key: string; value: string; clear?: boolean }>;
    },
  ) {
    await runAction(
      `save-core-connection:${entry.key}`,
      async () => {
        await requestJson(
          `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(entry.connectionKey)}`,
          {
            method: "PUT",
            body: JSON.stringify({
              ...payload,
              enabled: true,
            }),
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
        successMessage: tl("Conexão do agente salva e verificada."),
        errorMessage: tl("Não foi possível salvar a conexão deste agente."),
      },
    );
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
        successMessage: tl("Padrão do sistema importado para este agente."),
        errorMessage: tl("Não foi possível importar o padrão do sistema."),
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
        successMessage: tl("Conexão do agente removida."),
        errorMessage: tl("Não foi possível remover a conexão deste agente."),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={tl("Integracoes")}
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
                  onToggleEnabled={(enabled) => handleIntegrationToggle(selectedIntegration.key, enabled)}
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
                  onConnectOAuth={selectedIntegration.oauth_supported ? () => startOAuth(selectedIntegration.connectionKey) : undefined}
                  onConnectManual={selectedIntegration.kind === "mcp" && !selectedIntegration.mcpConnection ? () => setConnectingMcpServer(selectedIntegration) : undefined}
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
                  onDiscoverTools={selectedIntegration.kind === "mcp" ? () => discoverTools(selectedIntegration.key) : undefined}
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
                  {tl("Integracoes nativas estao ativas por padrao. Aqui voce gerencia integracoes adicionais.")}
                </p>

                <div className="relative mb-4">
                  <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]" />
                  <input
                    type="text"
                    value={integrationSearch}
                    onChange={(e) => setIntegrationSearch(e.target.value)}
                    placeholder={tl("Buscar integracoes...")}
                    className="field-shell pl-9 pr-3 text-[var(--text-primary)]"
                  />
                </div>

                {integrationEntries.length === 0 && !integrationsLoading ? (
                  <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
                    {tl("Nenhuma integracao adicional disponivel.")}
                  </div>
                ) : groupedIntegrations.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
                    {tl("Nenhuma integracao encontrada para esta busca.")}
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

      {connectingMcpServer && connectingMcpServer.kind === "mcp" && (
        <McpConnectionModal
          server={connectingMcpServer.mcpServer ?? {
            server_key: connectingMcpServer.key,
            display_name: connectingMcpServer.label,
            description: connectingMcpServer.description || "",
            transport_type: "stdio",
            enabled: true,
            env_schema_json: "[]",
          } as import("@/lib/control-plane").McpServerCatalogEntry}
          agentId={agentId}
          existingConnection={connectingMcpServer.mcpConnection}
          onClose={() => setConnectingMcpServer(null)}
          onSaved={async () => {
            setConnectingMcpServer(null);
            await refreshIntegrations();
            if (selectedIntegration) {
              selectIntegration(null);
              setTimeout(() => selectIntegration(connectingMcpServer.id), 100);
            }
          }}
        />
      )}

      {editingCoreConnection && editingCoreConnection.kind === "core" && (
        <CoreConnectionModal
          entry={editingCoreConnection}
          onClose={() => setEditingCoreConnection(null)}
          onSave={async (payload) => {
            await saveCoreConnection(editingCoreConnection, payload);
            setEditingCoreConnection(null);
          }}
        />
      )}
    </div>
  );
}
