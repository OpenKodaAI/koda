"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import { Search, Plus, Puzzle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Input } from "@/components/ui/input";
import { requestJson } from "@/lib/http-client";
import type { McpServerCatalogEntry } from "@/lib/control-plane";
import { McpServerCard } from "./mcp-server-card";
import { McpServerEditorModal } from "./mcp-server-editor-modal";
import {
  MCP_CATEGORY_KEYS,
  MCP_CATEGORY_LABELS,
  filterAllowedMcpCatalogEntries,
  isReservedMcpServerKey,
  buildSuggestedMcpCatalogEntry,
  type McpCategory,
} from "./mcp-catalog-utils";
import { useMcpCatalogSuggestions } from "@/hooks/use-mcp-catalog-suggestions";

/*  Category filter chip                                               */

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
      className={[
        "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors duration-200",
        active
          ? "border-[var(--interactive-active-border)] bg-[var(--interactive-active-top)] text-[var(--interactive-active-text)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-tertiary)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)]",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

/*  Suggested server chip                                              */

function SuggestedChip({
  name,
  exists,
  onClick,
}: {
  name: string;
  exists: boolean;
  onClick: () => void;
}) {
  const { t } = useAppI18n();
  return (
    <button
      type="button"
      disabled={exists}
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
        exists
          ? "cursor-default border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-quaternary)]"
          : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
      ].join(" ")}
      title={exists ? t("generated.controlPlane.ja_adicionado_2b8a8465") : undefined}
    >
      {!exists && <Plus size={12} />}
      {name}
    </button>
  );
}

/*  Main catalog component                                             */

export function McpServerCatalog() {
  const { t } = useAppI18n();
  const { servers: suggestedServers, isLoading: suggestedLoading } =
    useMcpCatalogSuggestions();

  // Server list state
  const [servers, setServers] = useState<McpServerCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<McpCategory | "all">("all");

  // Modal state
  const [editingServer, setEditingServer] = useState<McpServerCatalogEntry | null | "new">(null);
  const [editorMode, setEditorMode] = useState<"create" | "edit">("create");
  const [lockServerKey, setLockServerKey] = useState(false);
  const [saving, setSaving] = useState(false);

  // Fetch servers
  const fetchServers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const items = await requestJson<McpServerCatalogEntry[]>(
        "/api/control-plane/mcp/catalog",
      );
      setServers(filterAllowedMcpCatalogEntries(items));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_carregar_servidores_10a6594d"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  // Derived categories
  const categories = useMemo(() => {
    const seen = new Set<McpCategory>();
    for (const s of servers) {
      if (s.category) seen.add(s.category as McpCategory);
    }
    return Array.from(seen);
  }, [servers]);

  // Filtered list
  const filtered = useMemo(() => {
    let result = servers;
    if (activeCategory !== "all") {
      result = result.filter((s) => s.category === activeCategory);
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (s) =>
          s.display_name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.server_key.toLowerCase().includes(q),
      );
    }
    return result;
  }, [servers, activeCategory, search]);

  // Existing server keys for suggested dedup
  const existingKeys = useMemo(() => new Set(servers.map((s) => s.server_key)), [servers]);

  // Handlers
  const handleSave = async (
    serverKey: string,
    payload: Partial<McpServerCatalogEntry>,
  ) => {
    setSaving(true);
    try {
      await requestJson(`/api/control-plane/mcp/catalog/${serverKey}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      await fetchServers();
      setEditorMode("create");
      setLockServerKey(false);
      setEditingServer(null);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (serverKey: string) => {
    if (!window.confirm(t("generated.controlPlane.tem_certeza_que_deseja_remover_este_servidor_b779d61c"))) return;
    await requestJson(`/api/control-plane/mcp/catalog/${serverKey}`, {
      method: "DELETE",
    });
    await fetchServers();
  };

  const handleToggle = async (server: McpServerCatalogEntry) => {
    await requestJson(`/api/control-plane/mcp/catalog/${server.server_key}`, {
      method: "PUT",
      body: JSON.stringify({ ...server, enabled: !server.enabled }),
    });
    await fetchServers();
  };

  const handleAddSuggested = (serverKey: string) => {
    if (isReservedMcpServerKey(serverKey)) return;
    const suggested = suggestedServers.find((s) => s.server_key === serverKey);
    if (!suggested) return;
    setEditorMode("create");
    setLockServerKey(true);
    setEditingServer(buildSuggestedMcpCatalogEntry(suggested));
  };

  return (
    <div>
      {/* Hero */}
      <div>
        <div className="flex items-center gap-2">
          <Puzzle size={20} className="text-[var(--text-tertiary)]" />
          <h1 className="text-xl font-bold tracking-[-0.04em] text-[var(--text-primary)] sm:text-2xl">
            {t("generated.controlPlane.servidores_mcp_6dc46f21")}
          </h1>
        </div>
        <p className="mt-1.5 text-sm text-[var(--text-tertiary)]">
          {t(
            "generated.controlPlane.gerencie_servidores_do_model_context_protoco_eea4d009",
          )}
        </p>

        {/* Search + Filters + Add */}
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full max-w-sm flex-1">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-quaternary)]"
            />
            <Input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("generated.controlPlane.buscar_servidores_1682e2ce")}
              className="pl-9"
              aria-label={t("generated.controlPlane.buscar_servidores_mcp_2df67126")}
            />
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1" role="tablist" aria-label={t("generated.controlPlane.filtrar_por_categoria_282524cb")}>
              <CategoryChip
                label={t("generated.controlPlane.todos_d6337c41")}
                active={activeCategory === "all"}
                onClick={() => setActiveCategory("all")}
              />
              {categories.map((cat) => (
                <CategoryChip
                  key={cat}
                  label={t(MCP_CATEGORY_KEYS[cat], {
                    defaultValue: MCP_CATEGORY_LABELS[cat],
                  })}
                  active={activeCategory === cat}
                  onClick={() => setActiveCategory(cat)}
                />
              ))}
            </div>

            <button
              type="button"
              onClick={() => {
                setEditorMode("create");
                setLockServerKey(false);
                setEditingServer("new");
              }}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--interactive-active-text)] transition-all"
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
        </div>
      </div>

      {/* Suggested servers */}
      {servers.length < 4 && (
        <div className="mt-4">
          <span className="eyebrow mb-2 block text-[var(--text-quaternary)]">
            {t("generated.controlPlane.sugeridos_356a1292")}
          </span>
          {suggestedLoading ? (
            <div className="flex flex-wrap gap-2" aria-hidden>
              {Array.from({ length: 8 }).map((_, idx) => (
                <span
                  key={idx}
                  className="inline-block h-7 w-24 animate-pulse rounded-lg bg-[var(--surface-panel-soft)]"
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {suggestedServers.map((s) => (
                <SuggestedChip
                  key={s.server_key}
                  name={
                    s.i18n_keys?.display_name
                      ? t(s.i18n_keys.display_name, { defaultValue: s.display_name })
                      : s.display_name
                  }
                  exists={existingKeys.has(s.server_key)}
                  onClick={() => handleAddSuggested(s.server_key)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Server grid */}
      <div className="mt-4">
        {loading ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-hidden>
            {Array.from({ length: 6 }).map((_, idx) => (
              <div
                key={idx}
                className="h-[5.5rem] animate-pulse rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]"
              />
            ))}
          </div>
        ) : error ? (
          <div className="py-12 text-center text-sm text-[var(--tone-danger-text)]">
            {error}
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-sm text-[var(--text-quaternary)]">
            {servers.length === 0
              ? t("generated.controlPlane.nenhum_servidor_mcp_configurado_adicione_um__e0b0b184")
              : t("generated.controlPlane.nenhum_servidor_encontrado_a6a1a59d")}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <AnimatePresence>
              {filtered.map((server, idx) => (
                <motion.div
                  key={server.server_key}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{
                    delay: idx * 0.03,
                    duration: 0.3,
                    ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
                  }}
                >
                  <McpServerCard
                    server={server}
                    onEdit={() => {
                      setEditorMode("edit");
                      setLockServerKey(false);
                      setEditingServer(server);
                    }}
                    onDelete={() => handleDelete(server.server_key)}
                    onToggle={() => handleToggle(server)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Editor modal */}
      <AnimatePresence>
        {editingServer !== null ? (
          <McpServerEditorModal
            server={editingServer === "new" ? null : editingServer}
            mode={editorMode}
            lockServerKey={lockServerKey}
            onClose={() => {
              setEditorMode("create");
              setLockServerKey(false);
              setEditingServer(null);
            }}
            onSave={handleSave}
            saving={saving}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}
