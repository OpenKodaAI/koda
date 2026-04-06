"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Pencil, Plug, Search, ShieldCheck, Trash2 } from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { SecretInput } from "@/components/ui/secret-controls";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useBotEditor } from "@/hooks/use-bot-editor";
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
import { CompactGrantToggle } from "@/components/control-plane/shared/compact-grant-toggle";
import { requestJson } from "@/lib/http-client";
import {
  parseResourceAccessPolicy,
  serializeResourceAccessPolicy,
} from "@/lib/policy-serializers";
import { AnimatePresence, motion } from "framer-motion";
import { FADE_TRANSITION, EASE_OUT } from "@/components/control-plane/shared/motion-constants";
import { cn } from "@/lib/utils";
import {
  CATEGORY_LABELS,
} from "@/components/control-plane/system/integrations/integration-catalog-data";

/* ------------------------------------------------------------------ */
/*  Only these core integrations are shown in agent scope              */
/* ------------------------------------------------------------------ */

const VISIBLE_CORE_KEYS = new Set([
  "gws",
  "gh",
  "glab",
  "jira",
  "confluence",
]);

/* ------------------------------------------------------------------ */
/*  Category resolution                                                */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  Reusable sub-components                                            */
/* ------------------------------------------------------------------ */

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


/* ------------------------------------------------------------------ */
/*  Unified entry type for the merged variables + secrets list         */
/* ------------------------------------------------------------------ */

type UnifiedEntry =
  | { kind: "variable"; key: string; value: string }
  | { kind: "secret"; key: string; preview: string };

/* ------------------------------------------------------------------ */
/*  Main tab                                                           */
/* ------------------------------------------------------------------ */

export function TabEscopo() {
  const {
    state,
    core,
    systemSettings,
    updateAgentSpecField,
    updateField,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();

  /* ---- Unified entry form state ----------------------------------- */
  const [draftKey, setDraftKey] = useState("");
  const [draftValue, setDraftValue] = useState("");
  const [draftIsSecret, setDraftIsSecret] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingKind, setEditingKind] = useState<"variable" | "secret" | null>(null);

  const botId = state.bot.id;
  const resourcePolicy = useMemo(
    () => parseResourceAccessPolicy(state.resourceAccessPolicyJson),
    [state.resourceAccessPolicyJson],
  );

  /* ---- Integration data ------------------------------------------ */
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
    agentId: botId,
    coreIntegrations: integrations,
    integrationGrants: resourcePolicy.integration_grants ?? {},
  });

  /* Only show whitelisted core integrations + all MCP entries */
  const integrationEntries = useMemo(
    () => rawIntegrationEntries.filter((entry) => {
      if (entry.kind === "core") return VISIBLE_CORE_KEYS.has(entry.key);
      return true;
    }),
    [rawIntegrationEntries],
  );

  /* ---- Search & category grouping --------------------------------- */
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
    agentId: botId,
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

  /* ---- Shared resource options ----------------------------------- */
  const localSecrets = (state.bot.secrets ?? []).filter((item) => {
    const s = String(item.scope || "agent").toLowerCase();
    return s === "agent" || s === "bot";
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

  const localEnvEntries = useMemo(
    () =>
      Object.entries(resourcePolicy.local_env)
        .map(([key, value]) => ({ key, value }))
        .sort((left, right) => left.key.localeCompare(right.key)),
    [resourcePolicy.local_env],
  );

  /* ---- Build unified entries list --------------------------------- */
  const unifiedEntries: UnifiedEntry[] = useMemo(() => {
    const items: UnifiedEntry[] = [];
    for (const entry of localEnvEntries) {
      items.push({ kind: "variable", key: entry.key, value: entry.value });
    }
    for (const secret of localSecrets) {
      const secretKey = String(secret.secret_key || "");
      if (secretKey) {
        items.push({ kind: "secret", key: secretKey, preview: String(secret.preview || tl("mascarado")) });
      }
    }
    return items.sort((a, b) => a.key.localeCompare(b.key));
  }, [localEnvEntries, localSecrets, tl]);

  /* ---- Helpers --------------------------------------------------- */

  function updateResourcePolicy(
    patch: Partial<typeof resourcePolicy>,
  ) {
    updateAgentSpecField(
      "resourceAccessPolicyJson",
      serializeResourceAccessPolicy({ ...resourcePolicy, ...patch }),
    );
  }

  function toggleSelection(items: string[], value: string) {
    return items.includes(value) ? items.filter((item) => item !== value) : [...items, value];
  }

  /* ---- Integration grant handlers -------------------------------- */

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
          `/api/control-plane/agents/${botId}/connections/${encodeURIComponent(entry.connectionKey)}`,
          {
            method: "PUT",
            body: JSON.stringify({
              ...payload,
              enabled: true,
            }),
          },
        );
        await requestJson(
          `/api/control-plane/agents/${botId}/connections/${encodeURIComponent(entry.connectionKey)}/verify`,
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
          `/api/control-plane/agents/${botId}/connections/${encodeURIComponent(entry.connectionKey)}/import-default`,
          {
            method: "POST",
          },
        );
        await requestJson(
          `/api/control-plane/agents/${botId}/connections/${encodeURIComponent(entry.connectionKey)}/verify`,
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
          `/api/control-plane/agents/${botId}/connections/${encodeURIComponent(entry.connectionKey)}`,
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

  /* ---- Shared resource grant handlers ----------------------------- */

  function handleSharedVarToggle(value: string) {
    updateResourcePolicy({
      allowed_shared_env_keys: toggleSelection(grantedSharedKeys, value),
    });
  }

  function handleGlobalSecretToggle(value: string) {
    updateResourcePolicy({
      allowed_global_secret_keys: toggleSelection(grantedSecretKeys, value),
    });
  }

  /* ---- Unified entry form helpers --------------------------------- */

  function resetEntryForm() {
    setDraftKey("");
    setDraftValue("");
    setDraftIsSecret(false);
    setEditingKey(null);
    setEditingKind(null);
    updateField("secretKey", "");
    updateField("secretValue", "");
  }

  function beginEditVariable(key: string, value: string) {
    setEditingKey(key);
    setEditingKind("variable");
    setDraftKey(key);
    setDraftValue(value);
    setDraftIsSecret(false);
  }

  function beginEditSecret(secretKey: string) {
    setEditingKey(secretKey);
    setEditingKind("secret");
    setDraftKey(secretKey);
    setDraftValue("");
    setDraftIsSecret(true);
    updateField("secretKey", secretKey);
    updateField("secretValue", "");
  }

  function resolveLocalSecretScope(secretKey: string) {
    const matchedSecret = localSecrets.find(
      (secret) => String(secret.secret_key || "").toUpperCase() === secretKey.toUpperCase(),
    );
    return String(matchedSecret?.scope || "agent").toLowerCase() === "bot" ? "bot" : "agent";
  }

  /* ---- Save / delete handlers ------------------------------------ */

  async function handleSaveEntry() {
    const key = draftKey.trim().toUpperCase();
    if (!key) {
      showToast(tl("Informe o nome da chave."), "warning");
      return;
    }

    if (draftIsSecret) {
      /* Save as secret via API */
      const value = draftValue.trim();
      if (!value) {
        showToast(tl("Informe o valor do segredo."), "warning");
        return;
      }
      await runAction("save-secret", async () => {
        const scope = resolveLocalSecretScope(key);
        await requestJson(
          `/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=${scope}`,
          {
            method: "PUT",
            body: JSON.stringify({ value }),
          },
        );
        resetEntryForm();
        router.refresh();
      }, {
        successMessage: tl('Segredo "{{key}}" salvo.', { key }),
        errorMessage: tl("Erro ao salvar segredo."),
      });
    } else {
      /* Save as local env variable */
      const value = draftValue.trim();
      if (!value) {
        showToast(tl("Informe o valor da variavel."), "warning");
        return;
      }
      const nextLocalEnv = { ...resourcePolicy.local_env };
      if (editingKey && editingKind === "variable" && editingKey !== key) {
        delete nextLocalEnv[editingKey];
      }
      nextLocalEnv[key] = value;
      updateResourcePolicy({ local_env: nextLocalEnv });
      resetEntryForm();
      showToast(tl('Variavel "{{key}}" preparada no rascunho.', { key }), "success");
    }
  }

  function handleDeleteVariable(key: string) {
    const next = { ...resourcePolicy.local_env };
    delete next[key];
    updateResourcePolicy({ local_env: next });
    if (editingKey === key) {
      resetEntryForm();
    }
    showToast(tl('Variavel "{{key}}" removida do rascunho.', { key }), "success");
  }

  async function handleDeleteSecret(key: string) {
    await runAction(`delete-secret:${key}`, async () => {
      const scope = resolveLocalSecretScope(key);
      await requestJson(
        `/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=${scope}`,
        { method: "DELETE" },
      );
      if (editingKey === key) {
        resetEntryForm();
      }
      router.refresh();
    }, {
      successMessage: tl('Segredo "{{key}}" removido.', { key }),
      errorMessage: tl("Erro ao remover segredo."),
    });
  }

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="flex flex-col gap-6">

      {/* ============================================================ */}
      {/*  Section 1: Integrations (grid + detail)                      */}
      {/* ============================================================ */}
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={tl("Integracoes")}
          icon={Plug}
          dirty={state.dirty.agentSpec}
          defaultOpen
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
                      /* Core: update allow_actions / deny_actions */
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

                {/* Search bar */}
                <div className="relative mb-4">
                  <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]" />
                  <input
                    type="text"
                    value={integrationSearch}
                    onChange={(e) => setIntegrationSearch(e.target.value)}
                    placeholder={tl("Buscar integracoes...")}
                    className="field-shell w-full py-3 pl-9 pr-4 text-sm text-[var(--text-primary)]"
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

      {/* ============================================================ */}
      {/*  Section 2: Shared Resource Grants (compact)                  */}
      {/* ============================================================ */}
      <section className="flex flex-col gap-6 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Escopo de acesso do agente")}
          icon={ShieldCheck}
          dirty={state.dirty.agentSpec}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CompactGrantToggle
              title={tl("Variaveis compartilhadas")}
              options={sharedVarOptions}
              selected={grantedSharedKeys}
              onToggle={handleSharedVarToggle}
            />
            <CompactGrantToggle
              title={tl("Segredos globais")}
              options={globalSecretOptions}
              selected={grantedSecretKeys}
              onToggle={handleGlobalSecretToggle}
            />
          </div>
        </PolicyCard>
      </section>

      {/* ============================================================ */}
      {/*  Section 3: Unified Variables & Secrets                       */}
      {/* ============================================================ */}
      <section className="flex flex-col gap-6 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Variaveis e segredos")}
          description={tl("Variaveis e credenciais locais do agente.")}
          icon={KeyRound}
        >
          {/* ── Add / Edit form ──────────────────────────────────── */}
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-[1fr_1fr] gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{tl("Chave")}</span>
                <input
                  type="text"
                  className="field-shell px-4 py-3 text-sm text-[var(--text-primary)] font-mono"
                  value={draftKey}
                  onChange={(event) => setDraftKey(event.target.value.toUpperCase())}
                  placeholder="API_KEY"
                  disabled={editingKind === "secret" && Boolean(editingKey)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{tl("Valor")}</span>
                {draftIsSecret ? (
                  <SecretInput
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={editingKey ? tl("Novo valor") : tl("Cole o segredo aqui")}
                  />
                ) : (
                  <input
                    type="text"
                    className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={tl("Ex.: squad-platform")}
                  />
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setDraftIsSecret((prev) => !prev)}
                disabled={editingKind === "secret"}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all",
                  draftIsSecret
                    ? "border-[rgba(255,180,80,0.25)] bg-[rgba(255,180,80,0.08)] text-[rgba(255,200,120,0.9)]"
                    : "border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)]",
                  editingKind === "secret" ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-[var(--border-strong)]",
                )}
              >
                <KeyRound size={12} />
                {draftIsSecret ? tl("Segredo") : tl("Variavel publica")}
              </button>

              <div className="flex items-center gap-2">
                {editingKey && (
                  <button
                    type="button"
                    onClick={resetEntryForm}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)]"
                  >
                    {tl("Cancelar")}
                  </button>
                )}
                <AsyncActionButton
                  type="button"
                  size="sm"
                  loading={draftIsSecret ? isPending("save-secret") : false}
                  loadingLabel={tl("Salvando")}
                  onClick={handleSaveEntry}
                >
                  {editingKey ? tl("Salvar") : tl("Adicionar")}
                </AsyncActionButton>
              </div>
            </div>

            {editingKind === "secret" && editingKey && (
              <p className="text-xs text-[var(--text-quaternary)]">
                {tl("Substituindo o valor de")}{" "}
                <span className="font-mono text-[var(--text-secondary)]">{editingKey}</span>
                {". "}
                {tl("O valor atual continua mascarado.")}
              </p>
            )}
          </div>

          {/* ── Entries list ─────────────────────────────────────── */}
          {unifiedEntries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
              {tl("Nenhuma variavel ou segredo cadastrado.")}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <AnimatePresence>
                {unifiedEntries.map((entry) => (
                  <motion.div
                    key={`${entry.kind}:${entry.key}`}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={FADE_TRANSITION}
                  >
                    <div className="flex items-center gap-3 rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
                      {/* Key + badge */}
                      <div className="flex min-w-0 flex-1 items-center gap-2.5">
                        <span className="font-mono text-sm text-[var(--text-primary)] truncate">{entry.key}</span>
                        <span
                          className={cn(
                            "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                            entry.kind === "secret"
                              ? "bg-[rgba(255,180,80,0.1)] text-[rgba(255,200,120,0.85)]"
                              : "bg-[rgba(255,255,255,0.05)] text-[var(--text-quaternary)]",
                          )}
                        >
                          {entry.kind === "secret" ? tl("secret") : tl("public")}
                        </span>
                      </div>

                      {/* Value preview */}
                      <span className="hidden font-mono text-xs text-[var(--text-quaternary)] truncate max-w-[200px] md:block">
                        {entry.kind === "secret" ? "••••••••" : entry.value}
                      </span>

                      {/* Actions */}
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() =>
                            entry.kind === "variable"
                              ? beginEditVariable(entry.key, entry.value)
                              : beginEditSecret(entry.key)
                          }
                          className="rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(255,255,255,0.06)] hover:text-[var(--text-secondary)]"
                          aria-label={tl("Editar")}
                        >
                          <Pencil size={13} />
                        </button>
                        {entry.kind === "variable" ? (
                          <button
                            type="button"
                            onClick={() => handleDeleteVariable(entry.key)}
                            className="rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(255,110,110,0.08)] hover:text-[var(--tone-danger-text)]"
                            aria-label={tl("Remover")}
                          >
                            <Trash2 size={13} />
                          </button>
                        ) : (
                          <AsyncActionButton
                            type="button"
                            variant="danger"
                            size="sm"
                            className="!p-1.5 !rounded-md !border-0 !bg-transparent !shadow-none text-[var(--text-quaternary)] hover:!bg-[rgba(255,110,110,0.08)] hover:!text-[var(--tone-danger-text)]"
                            loading={isPending(`delete-secret:${entry.key}`)}
                            loadingLabel=""
                            onClick={() => handleDeleteSecret(entry.key)}
                            aria-label={tl("Remover")}
                          >
                            <Trash2 size={13} />
                          </AsyncActionButton>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </PolicyCard>
      </section>

      {/* MCP Connection Modal */}
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
          agentId={botId}
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
