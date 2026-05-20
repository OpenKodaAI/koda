"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Plus, Search } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { InlineSpinner } from "@/components/ui/async-feedback";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import type { McpServerCatalogEntry } from "@/lib/control-plane";
import { requestJson, toErrorMessage } from "@/lib/http-client";
import { cn } from "@/lib/utils";
import { buildSuggestedMcpCatalogEntry } from "@/components/control-plane/system/mcp/mcp-catalog-utils";
import { useMcpCatalogSuggestions } from "@/hooks/use-mcp-catalog-suggestions";
import { McpServerEditorModal } from "@/components/control-plane/system/mcp/mcp-server-editor-modal";
import { IntegrationConnectionModal } from "./integration-connection-modal";
import { IntegrationCard } from "./integration-card";
import { IntegrationDetailView } from "./integration-detail-view";
import {
  UNIFIED_CATEGORY_LABELS,
  buildUnifiedIntegrationEntries,
  filterUnifiedIntegrationEntries,
  groupUnifiedIntegrationEntries,
  type UnifiedIntegrationCategory,
  type UnifiedIntegrationEntry,
} from "./integration-marketplace-data";
import { ProviderGrid } from "./provider-grid";

function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors duration-200",
        active
          ? "border-[var(--interactive-active-border)] bg-[var(--interactive-active-top)] text-[var(--interactive-active-text)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-tertiary)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)]",
      )}
    >
      {label}
    </button>
  );
}

const EASE = [0.22, 1, 0.36, 1] as const;

const viewTransition = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
  transition: { duration: 0.28, ease: EASE as unknown as [number, number, number, number] },
} as const;

const viewTransitionReverse = {
  initial: { opacity: 0, x: -20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 20 },
  transition: { duration: 0.28, ease: EASE as unknown as [number, number, number, number] },
} as const;

type MarketplaceTab = "tools" | "providers";

type McpEditorState = {
  server: McpServerCatalogEntry | null;
  mode: "create" | "edit";
  lockServerKey: boolean;
};

function MarketplaceGrid({
  entries,
  mcpCatalogLoading,
  suggestedLoading,
  mcpCatalogError,
  onRetryMcpCatalog,
  onSelect,
  onAddCustomMcp,
}: {
  entries: UnifiedIntegrationEntry[];
  mcpCatalogLoading: boolean;
  /** True while the curated MCP catalog is being fetched from the API. */
  suggestedLoading: boolean;
  mcpCatalogError: string | null;
  onRetryMcpCatalog: () => void;
  onSelect: (entryId: string) => void;
  onAddCustomMcp: () => void;
}) {
  const { t, tl } = useAppI18n();
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<
    UnifiedIntegrationCategory | "all"
  >("all");

  const categories = useMemo(() => {
    const seen = new Set<UnifiedIntegrationCategory>();
    for (const entry of entries) {
      seen.add(entry.category);
    }
    return Array.from(seen);
  }, [entries]);

  const filtered = useMemo(
    () =>
      filterUnifiedIntegrationEntries(entries, {
        category: activeCategory,
        search,
      }),
    [activeCategory, entries, search],
  );

  const grouped = useMemo(
    () => groupUnifiedIntegrationEntries(filtered),
    [filtered],
  );

  let cardIndex = 0;

  return (
    <motion.div {...viewTransitionReverse}>
      <div className="integration-marketplace-hero">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-[-0.04em] text-[var(--text-primary)] sm:text-2xl">
              {t("generated.controlPlane.conecte_suas_ferramentas_de7a7271")}
            </h1>
            <p className="mt-1.5 max-w-2xl text-sm text-[var(--text-tertiary)]">
              {t(
                "generated.controlPlane.integre_com_plataformas_nativas_e_organize_t_dad92b64",
              )}
            </p>
          </div>

          <button
            type="button"
            onClick={onAddCustomMcp}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold text-[var(--interactive-active-text)] transition-all sm:shrink-0"
            style={{
              background:
                "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
              border: "1px solid var(--interactive-active-border)",
            }}
          >
            <Plus size={14} />
            {t("generated.controlPlane.adicionar_servidor_mcp_ea88d544")}
          </button>
        </div>

        <div className="mt-4 flex flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full max-w-sm flex-1">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]"
              />
              <input
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("generated.controlPlane.buscar_integracoes_e_servidores_2376bd3c")}
                className="field-shell pl-9 pr-3 text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
                aria-label={t("generated.controlPlane.buscar_integracoes_e_servidores_mcp_442e52fb")}
              />
            </div>

            <div
              className="flex flex-wrap items-center gap-1"
              role="tablist"
              aria-label={t("generated.controlPlane.filtrar_por_categoria_282524cb")}
            >
              <CategoryChip
                label={t("generated.controlPlane.todos_d6337c41")}
                active={activeCategory === "all"}
                onClick={() => setActiveCategory("all")}
              />
              {categories.map((category) => (
                <CategoryChip
                  key={category}
                  label={tl(UNIFIED_CATEGORY_LABELS[category])}
                  active={activeCategory === category}
                  onClick={() => setActiveCategory(category)}
                />
              ))}
            </div>
          </div>

          {mcpCatalogLoading ? (
            <div
              className="flex items-center py-1 text-[var(--text-quaternary)]"
              role="status"
              aria-label={t("generated.controlPlane.atualizando_estado_do_catalogo_mcp_51927d11")}
            >
              <InlineSpinner className="h-3.5 w-3.5" />
            </div>
          ) : null}

          {mcpCatalogError ? (
            <div className="flex flex-col gap-2 rounded-xl border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-4 py-3 text-sm text-[var(--tone-danger-text)] sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle size={14} className="shrink-0" />
                <span>{mcpCatalogError}</span>
              </div>
              <button
                type="button"
                onClick={onRetryMcpCatalog}
                className="inline-flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
              >
                {t("generated.controlPlane.tentar_novamente_14dc7f3f")}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {grouped.length === 0 && (suggestedLoading || mcpCatalogLoading) ? (
        <div className="mt-4 grid grid-cols-2 gap-2" aria-hidden>
          {Array.from({ length: 8 }).map((_, idx) => (
            <div
              key={idx}
              className="h-[5.5rem] animate-pulse rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]"
            />
          ))}
        </div>
      ) : grouped.length === 0 ? (
        <div className="py-12 text-center text-sm text-[var(--text-quaternary)]">
          {t("generated.controlPlane.nenhuma_integracao_ou_servidor_mcp_encontrad_eb198904")}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {grouped.map(({ category, entries: categoryEntries }) => (
            <div key={category}>
              <span className="eyebrow mb-2 block text-[var(--text-quaternary)]">
                {tl(UNIFIED_CATEGORY_LABELS[category])}
              </span>
              <div className="grid grid-cols-2 gap-2">
                {categoryEntries.map((entry) => {
                  const idx = cardIndex++;
                  return (
                    <motion.div
                      key={entry.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        delay: idx * 0.03,
                        duration: 0.3,
                        ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
                      }}
                    >
                      <IntegrationCard
                        entry={entry}
                        onClick={() => onSelect(entry.id)}
                      />
                    </motion.div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function TabBar({
  activeTab,
  onChange,
}: {
  activeTab: MarketplaceTab;
  onChange: (tab: MarketplaceTab) => void;
}) {
  const { t, tl } = useAppI18n();

  const tabs: { id: MarketplaceTab; label: string }[] = [
    { id: "tools", label: t("generated.controlPlane.ferramentas_c76ec58e") },
    { id: "providers", label: t("generated.controlPlane.provedores_ai_cd03be96") },
  ];

  return (
    <div className="mb-4 flex items-center gap-1 border-b border-[var(--border-subtle)]">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "relative px-4 py-2.5 text-sm font-medium transition-colors",
            activeTab === tab.id
              ? "text-[var(--text-primary)]"
              : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]",
          )}
        >
          {tab.label}
          {activeTab === tab.id ? (
            <motion.div
              layoutId="marketplace-tab-indicator"
              className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--text-primary)]"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function IntegrationMarketplace() {
  const { t, tl } = useAppI18n();
  const {
    draft,
    integrationConnections,
  } = useSystemSettings();

  const [activeTab, setActiveTab] = useState<MarketplaceTab>("tools");
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [connectingEntryId, setConnectingEntryId] = useState<string | null>(null);
  const [mcpCatalog, setMcpCatalog] = useState<McpServerCatalogEntry[]>([]);
  const [mcpCatalogLoading, setMcpCatalogLoading] = useState(false);
  const [mcpCatalogError, setMcpCatalogError] = useState<string | null>(null);
  const [mcpEditorState, setMcpEditorState] = useState<McpEditorState | null>(null);
  const [mcpSaving, setMcpSaving] = useState(false);
  const [mcpRemovingServerKey, setMcpRemovingServerKey] = useState<string | null>(null);

  const fetchMcpCatalog = useCallback(async () => {
    try {
      setMcpCatalogLoading(true);
      setMcpCatalogError(null);
      const items = await requestJson<McpServerCatalogEntry[]>(
        "/api/control-plane/mcp/catalog",
      );
      setMcpCatalog(items);
    } catch (error) {
      setMcpCatalogError(
        toErrorMessage(error, t("generated.controlPlane.erro_ao_carregar_catalogo_mcp_1527c12c")),
      );
    } finally {
      setMcpCatalogLoading(false);
    }
  }, [t, tl]);

  useEffect(() => {
    void fetchMcpCatalog();
  }, [fetchMcpCatalog]);

  const { servers: suggestedMcpServers, isLoading: suggestedLoading } =
    useMcpCatalogSuggestions();

  const unifiedEntries = useMemo(
    () =>
      buildUnifiedIntegrationEntries({
        integrations: draft.values.resources.integrations ?? {},
        integrationConnections,
        mcpCatalog,
        suggestedMcpServers,
      }),
    [
      draft.values.resources.integrations,
      integrationConnections,
      mcpCatalog,
      suggestedMcpServers,
    ],
  );

  const selectedEntry = useMemo(
    () =>
      selectedEntryId
        ? unifiedEntries.find((entry) => entry.id === selectedEntryId) ?? null
        : null,
    [selectedEntryId, unifiedEntries],
  );

  const connectingEntry = useMemo(() => {
    if (!connectingEntryId) {
      return null;
    }
    const match = unifiedEntries.find((entry) => entry.id === connectingEntryId);
    return match?.kind === "core" ? match.core?.entry ?? null : null;
  }, [connectingEntryId, unifiedEntries]);

  const handleTabChange = useCallback((tab: MarketplaceTab) => {
    setActiveTab(tab);
    setSelectedEntryId(null);
    setConnectingEntryId(null);
    setMcpEditorState(null);
    setMcpRemovingServerKey(null);
  }, []);

  const openCustomMcpEditor = useCallback(() => {
    setMcpEditorState({
      server: null,
      mode: "create",
      lockServerKey: false,
    });
  }, []);

  const handleOpenMcpEditor = useCallback((entry: UnifiedIntegrationEntry) => {
    if (entry.kind !== "mcp" || !entry.mcp) {
      return;
    }

    if (entry.mcp.canAdd && entry.mcp.suggested) {
      setMcpEditorState({
        server: buildSuggestedMcpCatalogEntry(entry.mcp.suggested),
        mode: "create",
        lockServerKey: true,
      });
      return;
    }

    if (entry.mcp.server) {
      setMcpEditorState({
        server: entry.mcp.server,
        mode: "edit",
        lockServerKey: false,
      });
    }
  }, []);

  const handleSaveMcpServer = useCallback(
    async (serverKey: string, payload: Partial<McpServerCatalogEntry>) => {
      try {
        setMcpSaving(true);
        await requestJson(`/api/control-plane/mcp/catalog/${serverKey}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        await fetchMcpCatalog();
        setSelectedEntryId(`mcp:${serverKey}`);
        setMcpEditorState(null);
      } finally {
        setMcpSaving(false);
      }
    },
    [fetchMcpCatalog],
  );

  const handleRemoveMcpServer = useCallback(
    async (entry: UnifiedIntegrationEntry) => {
      if (entry.kind !== "mcp" || !entry.mcp?.serverKey) {
        return;
      }

      if (
        !window.confirm(
          t(
            "generated.controlPlane.tem_certeza_que_deseja_remover_este_servidor_ba06126c",
          ),
        )
      ) {
        return;
      }

      const serverKey = entry.mcp.serverKey;

      try {
        setMcpRemovingServerKey(serverKey);
        await requestJson(`/api/control-plane/mcp/catalog/${serverKey}`, {
          method: "DELETE",
        });
        await fetchMcpCatalog();
        if (selectedEntryId === entry.id) {
          setSelectedEntryId(null);
        }
      } finally {
        setMcpRemovingServerKey(null);
      }
    },
    [fetchMcpCatalog, selectedEntryId, t, tl],
  );

  return (
    <>
      <TabBar activeTab={activeTab} onChange={handleTabChange} />

      <AnimatePresence mode="wait">
        {activeTab === "tools" ? (
          selectedEntry ? (
            <motion.div key={`detail:${selectedEntry.id}`} {...viewTransition}>
              <IntegrationDetailView
                entry={selectedEntry}
                onBack={() => setSelectedEntryId(null)}
                onConnect={() => setConnectingEntryId(selectedEntry.id)}
                onOpenMcpEditor={handleOpenMcpEditor}
                onRemoveMcpServer={handleRemoveMcpServer}
                mcpRemoving={mcpRemovingServerKey === selectedEntry.mcp?.serverKey}
              />
            </motion.div>
          ) : (
            <MarketplaceGrid
              key="grid"
              entries={unifiedEntries}
              mcpCatalogLoading={mcpCatalogLoading}
              suggestedLoading={suggestedLoading}
              mcpCatalogError={mcpCatalogError}
              onRetryMcpCatalog={() => {
                void fetchMcpCatalog();
              }}
              onSelect={setSelectedEntryId}
              onAddCustomMcp={openCustomMcpEditor}
            />
          )
        ) : (
          <motion.div
            key="providers"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: EASE as unknown as [number, number, number, number] }}
          >
            <ProviderGrid />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {connectingEntry ? (
          <IntegrationConnectionModal
            entry={connectingEntry}
            onClose={() => setConnectingEntryId(null)}
          />
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {mcpEditorState ? (
          <McpServerEditorModal
            server={mcpEditorState.server}
            mode={mcpEditorState.mode}
            lockServerKey={mcpEditorState.lockServerKey}
            onClose={() => setMcpEditorState(null)}
            onSave={handleSaveMcpServer}
            saving={mcpSaving}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}
