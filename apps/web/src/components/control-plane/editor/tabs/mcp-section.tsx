"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  Puzzle,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { requestJson } from "@/lib/http-client";
import type {
  McpAgentConnection,
  McpDiscoveredTool,
  McpServerCatalogEntry,
  McpToolPolicy,
  McpToolPolicyEntry,
} from "@/lib/control-plane";
import {
  MCP_SUGGESTED_SERVERS,
  filterAllowedMcpCatalogEntries,
  type McpExpectedTool,
} from "@/components/control-plane/system/mcp/mcp-catalog-data";
import { McpConnectionModal } from "./mcp-connection-modal";
import { McpToolPolicyRow } from "./mcp-tool-policy-row";

type McpSectionProps = {
  agentId: string;
};

type ServerWithState = {
  server: McpServerCatalogEntry;
  connection: McpAgentConnection | null;
  tools: McpDiscoveredTool[];
  policies: Record<string, McpToolPolicy>;
  expanded: boolean;
  discovering: boolean;
  disconnecting: boolean;
};

function connectionStatus(
  connection: McpAgentConnection | null,
): "desconectado" | "conectado" | "erro" {
  if (!connection) return "desconectado";
  if (connection.last_error) return "erro";
  return "conectado";
}

function StatusBadge({
  status,
  tl,
}: {
  status: "desconectado" | "conectado" | "erro";
  tl: (v: string) => string;
}) {
  if (status === "conectado") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2.5 py-0.5 text-[10px] font-medium text-[var(--tone-success-text)]">
        <CheckCircle2 size={10} />
        {tl("Conectado")}
      </span>
    );
  }
  if (status === "erro") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2.5 py-0.5 text-[10px] font-medium text-[var(--tone-danger-text)]">
        <XCircle size={10} />
        {tl("Erro")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-2.5 py-0.5 text-[10px] font-medium text-[var(--text-quaternary)]">
      {tl("Desconectado")}
    </span>
  );
}

function TransportBadge({ type }: { type: string }) {
  return (
    <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-quaternary)]">
      {type === "http_sse" ? "HTTP/SSE" : type === "stdio" ? "stdio" : type}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Read-only expected tool preview (disconnected servers)              */
/* ------------------------------------------------------------------ */

function ExpectedToolRow({ tool, tl }: { tool: McpExpectedTool; tl: (v: string) => string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-[var(--text-secondary)]">
          {tool.name}
        </span>
        {tool.read_only_hint && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-info-text)]">
            {tl("Somente leitura")}
          </span>
        )}
        {tool.destructive_hint && (
          <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-danger-text)]">
            {tl("Destrutivo")}
          </span>
        )}
      </div>
      {tool.description && (
        <p className="text-xs leading-relaxed text-[var(--text-quaternary)]">
          {tool.description}
        </p>
      )}
    </div>
  );
}

export function McpSection({ agentId }: McpSectionProps) {
  const { tl } = useAppI18n();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [servers, setServers] = useState<ServerWithState[]>([]);
  const [modalServer, setModalServer] = useState<McpServerCatalogEntry | null>(null);
  const [modalExistingConnection, setModalExistingConnection] =
    useState<McpAgentConnection | null>(null);

  // Fetch catalog + connections on mount
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [catalog, connections] = await Promise.all([
        requestJson<McpServerCatalogEntry[]>(
          "/api/control-plane/mcp/catalog",
        ),
        requestJson<McpAgentConnection[]>(
          `/api/control-plane/agents/${agentId}/mcp/connections`,
        ),
      ]);
      const connectionMap = new Map<string, McpAgentConnection>();
      for (const conn of connections) {
        connectionMap.set(conn.server_key, conn);
      }

      // For connected servers, load cached tools & policies
      const serverStates: ServerWithState[] = [];
      for (const server of filterAllowedMcpCatalogEntries(catalog)) {
        const conn = connectionMap.get(server.server_key) ?? null;
        let tools: McpDiscoveredTool[] = [];
        const policies: Record<string, McpToolPolicy> = {};

        if (conn) {
          // Parse cached tools
          try {
            tools = conn.cached_tools_json
              ? JSON.parse(conn.cached_tools_json)
              : [];
          } catch {
            tools = [];
          }

          // Load policies if we have tools
          if (tools.length > 0) {
            try {
              const policyEntries = await requestJson<McpToolPolicyEntry[]>(
                `/api/control-plane/agents/${agentId}/mcp/connections/${server.server_key}/policies`,
              );
              for (const entry of policyEntries) {
                policies[entry.tool_name] = entry.policy;
              }
            } catch {
              // Policies are optional; proceed without them
            }
          }
        }

        serverStates.push({
          server,
          connection: conn,
          tools,
          policies,
          expanded: false,
          discovering: false,
          disconnecting: false,
        });
      }

      setServers(serverStates);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : tl("Erro ao carregar servidores MCP"),
      );
    } finally {
      setLoading(false);
    }
  }, [agentId, tl]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const connectedCount = useMemo(
    () => servers.filter((s) => s.connection !== null).length,
    [servers],
  );

  const summaryLabel = loading
    ? tl("Carregando...")
    : servers.length === 0
      ? tl("Nenhum servidor MCP disponivel")
      : connectedCount > 0
        ? `${connectedCount} servidor(es) conectado(s)`
        : tl("Nenhum servidor conectado");

  // Lookup expected tools from catalog for disconnected server previews
  const expectedToolsMap = useMemo(() => {
    const map = new Map<string, McpExpectedTool[]>();
    for (const s of MCP_SUGGESTED_SERVERS) {
      if (s.expected_tools.length > 0) {
        map.set(s.server_key, s.expected_tools);
      }
    }
    return map;
  }, []);

  const toggleExpanded = useCallback((serverKey: string) => {
    setServers((prev) =>
      prev.map((s) =>
        s.server.server_key === serverKey
          ? { ...s, expanded: !s.expanded }
          : s,
      ),
    );
  }, []);

  const handleConnect = useCallback(
    (server: McpServerCatalogEntry, existingConnection: McpAgentConnection | null) => {
      setModalServer(server);
      setModalExistingConnection(existingConnection);
    },
    [],
  );

  const handleModalClose = useCallback(() => {
    setModalServer(null);
    setModalExistingConnection(null);
  }, []);

  const handleDiscover = useCallback(
    async (serverKey: string) => {
      setServers((prev) =>
        prev.map((s) =>
          s.server.server_key === serverKey
            ? { ...s, discovering: true }
            : s,
        ),
      );
      try {
        const result = await requestJson<{ tools: McpDiscoveredTool[] }>(
          `/api/control-plane/agents/${agentId}/mcp/connections/${serverKey}/discover`,
          { method: "POST" },
        );
        setServers((prev) =>
          prev.map((s) =>
            s.server.server_key === serverKey
              ? {
                  ...s,
                  tools: result.tools ?? [],
                  discovering: false,
                  expanded: true,
                }
              : s,
          ),
        );
      } catch {
        setServers((prev) =>
          prev.map((s) =>
            s.server.server_key === serverKey
              ? { ...s, discovering: false }
              : s,
          ),
        );
      }
    },
    [agentId],
  );

  const handleModalSaved = useCallback(async () => {
    const savedServerKey = modalServer?.server_key;
    setModalServer(null);
    setModalExistingConnection(null);
    await fetchData();
    // Auto-discover tools for the just-connected server
    if (savedServerKey) {
      handleDiscover(savedServerKey);
    }
  }, [fetchData, modalServer?.server_key, handleDiscover]);

  const handleDisconnect = useCallback(
    async (serverKey: string) => {
      if (!window.confirm(tl("Tem certeza que deseja desconectar? As credenciais serao removidas."))) return;
      setServers((prev) =>
        prev.map((s) =>
          s.server.server_key === serverKey
            ? { ...s, disconnecting: true }
            : s,
        ),
      );
      try {
        await requestJson(
          `/api/control-plane/agents/${agentId}/mcp/connections/${serverKey}`,
          { method: "DELETE" },
        );
        await fetchData();
      } catch {
        setServers((prev) =>
          prev.map((s) =>
            s.server.server_key === serverKey
              ? { ...s, disconnecting: false }
              : s,
          ),
        );
      }
    },
    [agentId, fetchData, tl],
  );

  const handlePolicyChange = useCallback(
    async (serverKey: string, toolName: string, policy: McpToolPolicy) => {
      // Optimistic update
      setServers((prev) =>
        prev.map((s) =>
          s.server.server_key === serverKey
            ? { ...s, policies: { ...s.policies, [toolName]: policy } }
            : s,
        ),
      );

      try {
        await requestJson(
          `/api/control-plane/agents/${agentId}/mcp/connections/${serverKey}/policies/${toolName}`,
          { method: "PUT", body: JSON.stringify({ policy }) },
        );
      } catch {
        // Revert on error
        setServers((prev) =>
          prev.map((s) =>
            s.server.server_key === serverKey
              ? {
                  ...s,
                  policies: {
                    ...s.policies,
                    [toolName]: s.policies[toolName] ?? "auto",
                  },
                }
              : s,
          ),
        );
      }
    },
    [agentId],
  );

  return (
    <>
      <PolicyCard
        title={tl("Servidores MCP")}
        description={summaryLabel}
        icon={Puzzle}
      >
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-[var(--text-tertiary)]" />
            <span className="ml-2 text-sm text-[var(--text-tertiary)]">
              {tl("Carregando servidores...")}
            </span>
          </div>
        )}

        {error && !loading && (
          <div className="flex items-center gap-2 rounded-xl border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-4 py-3">
            <AlertCircle size={14} className="shrink-0 text-[var(--tone-danger-text)]" />
            <span className="text-xs text-[var(--tone-danger-text)]">{error}</span>
            <button
              type="button"
              onClick={fetchData}
              className="ml-auto text-xs text-[var(--text-secondary)] underline hover:text-[var(--text-primary)]"
            >
              {tl("Tentar novamente")}
            </button>
          </div>
        )}

        {!loading && !error && servers.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Puzzle size={24} className="text-[var(--text-quaternary)]" />
            <p className="text-sm text-[var(--text-tertiary)]">
              {tl("Nenhum servidor MCP disponivel no catalogo.")}
            </p>
            <p className="text-xs text-[var(--text-quaternary)]">
              {tl(
                "Configure servidores MCP no catalogo do sistema para conecta-los a este agente.",
              )}
            </p>
          </div>
        )}

        {!loading && !error && servers.length > 0 && (
          <div className="flex flex-col gap-3">
            {servers.map((item) => {
              const status = connectionStatus(item.connection);
              const isConnected = status !== "desconectado";

              return (
                <div
                  key={item.server.server_key}
                  className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] transition-colors"
                >
                  {/* Server card header */}
                  <div className="flex items-center gap-3 px-4 py-3.5">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-tint)]">
                      <Puzzle
                        size={15}
                        className={
                          isConnected
                            ? "text-[var(--tone-info-dot)]"
                            : "text-[var(--text-quaternary)]"
                        }
                      />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-[var(--text-primary)]">
                          {item.server.display_name}
                        </span>
                        <TransportBadge type={item.server.transport_type} />
                        <StatusBadge status={status} tl={tl} />
                      </div>
                      {item.server.description && (
                        <p className="mt-0.5 text-xs text-[var(--text-quaternary)] line-clamp-1">
                          {item.server.description}
                        </p>
                      )}
                      {item.connection?.last_error && (
                        <p className="mt-1 text-[11px] text-[var(--tone-danger-text)]">
                          {item.connection.last_error}
                        </p>
                      )}
                      {isConnected && item.discovering && (
                        <p className="mt-1 flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]">
                          <Loader2 size={10} className="animate-spin" />
                          {tl("Descobrindo tools...")}
                        </p>
                      )}
                      {isConnected && !item.discovering && item.tools.length === 0 && (
                        <p className="mt-1 text-[11px] text-[var(--text-quaternary)]">
                          {tl("Conectado (sem tools descobertas)")}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex shrink-0 items-center gap-2">
                      {isConnected && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleDiscover(item.server.server_key)}
                            disabled={item.discovering}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
                            title={tl("Descobrir tools")}
                          >
                            {item.discovering ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <RefreshCw size={12} />
                            )}
                            <span className="hidden sm:inline">
                              {tl("Descobrir tools")}
                            </span>
                          </button>

                          {item.tools.length > 0 && (
                            <button
                              type="button"
                              onClick={() => toggleExpanded(item.server.server_key)}
                              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                            >
                              {item.tools.length} ferramenta(s)
                              {item.expanded ? (
                                <ChevronDown size={12} />
                              ) : (
                                <ChevronRight size={12} />
                              )}
                            </button>
                          )}

                          <button
                            type="button"
                            onClick={() =>
                              handleDisconnect(item.server.server_key)
                            }
                            disabled={item.disconnecting}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2.5 py-1.5 text-xs text-[var(--tone-danger-text)] transition-colors hover:bg-[var(--tone-danger-bg-strong)] disabled:opacity-50"
                            title={tl("Desconectar")}
                          >
                            {item.disconnecting ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <Trash2 size={12} />
                            )}
                            <span className="hidden sm:inline">
                              {tl("Desconectar")}
                            </span>
                          </button>
                        </>
                      )}

                      {!isConnected && (
                        <>
                          {(expectedToolsMap.get(item.server.server_key)?.length ?? 0) > 0 && (
                            <button
                              type="button"
                              onClick={() => toggleExpanded(item.server.server_key)}
                              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)]"
                            >
                              {expectedToolsMap.get(item.server.server_key)!.length} ferramenta(s)
                              {item.expanded ? (
                                <ChevronDown size={12} />
                              ) : (
                                <ChevronRight size={12} />
                              )}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              handleConnect(item.server, item.connection)
                            }
                            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--interactive-active-text)] transition-all"
                            style={{
                              background:
                                "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                              border:
                                "1px solid var(--interactive-active-border)",
                            }}
                          >
                            <Plus size={12} />
                            {tl("Conectar")}
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Expanded tool list (connected servers) */}
                  <AnimatePresence initial={false}>
                    {item.expanded && isConnected && item.tools.length > 0 && (
                      <motion.div
                        key="tools"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{
                          duration: 0.25,
                          ease: [0.22, 1, 0.36, 1],
                        }}
                        className="overflow-hidden"
                      >
                        <div className="flex flex-col gap-2 border-t border-[var(--border-subtle)] px-4 pb-4 pt-3">
                          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                            {tl("Tools descobertas")} ({item.tools.length})
                          </div>
                          {item.tools.map((tool) => (
                            <McpToolPolicyRow
                              key={tool.name}
                              agentId={agentId}
                              serverKey={item.server.server_key}
                              tool={tool}
                              currentPolicy={
                                item.policies[tool.name] ?? "auto"
                              }
                              onPolicyChange={(toolName, policy) =>
                                handlePolicyChange(
                                  item.server.server_key,
                                  toolName,
                                  policy,
                                )
                              }
                            />
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Expected tools preview (disconnected servers) */}
                  <AnimatePresence initial={false}>
                    {item.expanded && !isConnected && (expectedToolsMap.get(item.server.server_key)?.length ?? 0) > 0 && (
                      <motion.div
                        key="expected-tools"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{
                          duration: 0.25,
                          ease: [0.22, 1, 0.36, 1],
                        }}
                        className="overflow-hidden"
                      >
                        <div className="flex flex-col gap-2 border-t border-dashed border-[var(--border-subtle)] px-4 pb-4 pt-3">
                          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                            {tl("Tools esperadas")} ({expectedToolsMap.get(item.server.server_key)!.length})
                          </div>
                          {expectedToolsMap.get(item.server.server_key)!.map((tool) => (
                            <ExpectedToolRow key={tool.name} tool={tool} tl={tl} />
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        )}
      </PolicyCard>

      {/* Connection modal */}
      <AnimatePresence>
        {modalServer && (
          <McpConnectionModal
            server={modalServer}
            agentId={agentId}
            existingConnection={modalExistingConnection}
            onClose={handleModalClose}
            onSaved={handleModalSaved}
          />
        )}
      </AnimatePresence>
    </>
  );
}
