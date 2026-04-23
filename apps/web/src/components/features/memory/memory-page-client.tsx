"use client";

import dynamic from "next/dynamic";
import {
  Suspense,
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  BrainCircuit,
  RefreshCcw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-primitives";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  SELECT_ALL_VALUE,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  MemoryGraphEdge,
  MemoryGraphNode,
  MemoryLearningNode,
  MemoryMapResponse,
  MemoryTypeKey,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { getMemoryTypeLabel, getMemoryTypeMeta } from "@/lib/memory-constants";
import { fetchMemoryMap } from "@/components/memory/memory-dashboard-api";
import { MemoryInspector } from "@/components/memory/memory-inspector";

const MemoryGraphCanvas = dynamic(
  () =>
    import("@/components/memory/memory-graph/memory-graph-canvas").then((module) => ({
      default: module.MemoryGraphCanvas,
    })),
  {
    loading: () => (
      <div className="min-h-[520px] w-full animate-pulse rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]" />
    ),
  },
);

const MemoryCurationWorkspace = dynamic(
  () =>
    import("@/components/memory/memory-curation-workspace").then((module) => ({
      default: module.MemoryCurationWorkspace,
    })),
  {
    loading: () => (
      <div className="min-h-[420px] w-full animate-pulse rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] sm:min-h-[560px]" />
    ),
  },
);

type MemoryNode = MemoryGraphNode | MemoryLearningNode;
type EdgeVisibility = {
  semantic: boolean;
  session: boolean;
  source: boolean;
};
type MemoryView = "map" | "curation";
type MetricTone = "neutral" | "accent" | "warning" | "danger" | "success";

const DAY_OPTIONS = [7, 30, 90] as const;
const DEFAULT_EDGE_VISIBILITY: EdgeVisibility = {
  semantic: true,
  session: true,
  source: true,
};

function MemoryEmptyStateCard() {
  const { t } = useAppI18n();
  return (
    <div className="flex min-h-[460px] w-full items-center justify-center rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]">
      <PageEmptyState
        icon={BrainCircuit}
        title={t("memory.empty.title", { defaultValue: "Sem memórias ainda" })}
        description={t("memory.empty.description", {
          defaultValue: "As memórias aparecerão aqui como uma rede de pontos conectados.",
        })}
      />
    </div>
  );
}

interface MemoryFiltersPanelProps {
  data: MemoryMapResponse;
  search: string;
  onSearchChange: (value: string) => void;
  userId: number | null;
  onUserChange: (value: number | null) => void;
  sessionId: string | null;
  onSessionChange: (value: string | null) => void;
  days: number;
  onDaysChange: (value: number) => void;
  includeInactive: boolean;
  onIncludeInactiveChange: (value: boolean) => void;
  selectedTypes: MemoryTypeKey[];
  onToggleType: (value: MemoryTypeKey) => void;
  edgeVisibility: EdgeVisibility;
  onToggleEdge: (key: keyof EdgeVisibility) => void;
  onReset: () => void;
  searchInputRef?: React.Ref<HTMLInputElement>;
}

function MemoryFiltersPanel({
  data,
  search,
  onSearchChange,
  userId,
  onUserChange,
  sessionId,
  onSessionChange,
  days,
  onDaysChange,
  includeInactive,
  onIncludeInactiveChange,
  selectedTypes,
  onToggleType,
  edgeVisibility,
  onToggleEdge,
  onReset,
  searchInputRef,
}: MemoryFiltersPanelProps) {
  const { t } = useAppI18n();
  const edgeControls: Array<{ key: keyof EdgeVisibility; label: string }> = [
    { key: "semantic", label: t("memory.filters.edges.semantic", { defaultValue: "Semânticas" }) },
    { key: "session", label: t("memory.filters.edges.session", { defaultValue: "Sessão" }) },
    { key: "source", label: t("memory.filters.edges.source", { defaultValue: "Origem" }) },
  ];

  return (
    <div className="flex w-[320px] max-w-[86vw] flex-col gap-4 p-3">
      <header className="flex items-center justify-between">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[color:var(--text-quaternary)]">
          {t("memory.filters.title", { defaultValue: "Filtros" })}
        </p>
        <button
          type="button"
          onClick={onReset}
          className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-tertiary)] transition-colors hover:text-[color:var(--text-primary)]"
        >
          {t("common.clear", { defaultValue: "Limpar" })}
        </button>
      </header>

      <label className="block">
        <span className="mb-1.5 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
          {t("memory.filters.search", { defaultValue: "Buscar" })}
        </span>
        <div className="relative">
          <Search className="icon-xs absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--text-quaternary)]" />
          <input
            ref={searchInputRef}
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={t("memory.filters.searchPlaceholder", { defaultValue: "palavras-chave" })}
            className="h-9 w-full rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] pl-8 pr-3 text-[0.8125rem] text-[color:var(--text-primary)] placeholder:text-[color:var(--text-quaternary)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent)]"
          />
          {search ? (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              aria-label={t("common.clear", { defaultValue: "Limpar" })}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-[var(--radius-chip)] p-1 text-[color:var(--text-quaternary)] transition-colors hover:bg-[color:var(--hover-tint)] hover:text-[color:var(--text-primary)]"
            >
              <X className="icon-xs" />
            </button>
          ) : null}
        </div>
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="mb-1.5 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
            {t("common.user", { defaultValue: "Usuário" })}
          </span>
          <Select
            value={userId != null ? String(userId) : SELECT_ALL_VALUE}
            onValueChange={(v) =>
              onUserChange(v === SELECT_ALL_VALUE ? null : Number(v))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SELECT_ALL_VALUE}>
                {t("common.allUsers", { defaultValue: "Todos" })}
              </SelectItem>
              {data.filters.users.map((user) => (
                <SelectItem key={user.user_id} value={String(user.user_id)}>
                  {user.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="block">
          <span className="mb-1.5 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
            {t("common.session", { defaultValue: "Sessão" })}
          </span>
          <Select
            value={sessionId ?? SELECT_ALL_VALUE}
            onValueChange={(v) =>
              onSessionChange(v === SELECT_ALL_VALUE ? null : v)
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SELECT_ALL_VALUE}>
                {t("common.allSessions", { defaultValue: "Todas" })}
              </SelectItem>
              {data.filters.sessions.map((session) => (
                <SelectItem key={session.session_id} value={session.session_id}>
                  {session.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
      </div>

      <div>
        <span className="mb-1.5 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
          {t("memory.filters.timeWindow", { defaultValue: "Janela" })}
        </span>
        <div className="grid grid-cols-3 gap-1 rounded-[var(--radius-pill)] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] p-0.5">
          {DAY_OPTIONS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onDaysChange(value)}
              className={cn(
                "h-8 rounded-[var(--radius-pill)] font-mono text-[10.5px] uppercase tracking-[0.12em] transition-colors",
                days === value
                  ? "bg-[color:var(--panel-strong)] text-[color:var(--text-primary)]"
                  : "text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)]",
              )}
              aria-pressed={days === value}
            >
              {value}d
            </button>
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={() => onIncludeInactiveChange(!includeInactive)}
        className={cn(
          "flex h-9 items-center justify-between rounded-[var(--radius-input)] border px-3 text-[0.8125rem] transition-colors",
          includeInactive
            ? "border-[color:var(--accent)] bg-[color:var(--accent-muted)] text-[color:var(--text-primary)]"
            : "border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-primary)]",
        )}
      >
        <span>{t("memory.filters.includeInactive", { defaultValue: "Incluir inativas" })}</span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.12em]">
          {includeInactive
            ? t("common.on", { defaultValue: "on" })
            : t("common.off", { defaultValue: "off" })}
        </span>
      </button>

      <div>
        <span className="mb-2 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
          {t("memory.map.filterTitle", { defaultValue: "Tipos" })}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {data.filters.types.map((type) => {
            const active = selectedTypes.length === 0 || selectedTypes.includes(type.value);
            const meta = getMemoryTypeMeta(type.value);
            return (
              <button
                key={type.value}
                type="button"
                onClick={() => onToggleType(type.value)}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-pill)] border px-2.5 text-[0.75rem] transition-colors",
                  active
                    ? "border-[color:var(--border-subtle)] bg-[color:var(--panel)] text-[color:var(--text-primary)]"
                    : "border-transparent bg-transparent text-[color:var(--text-quaternary)] hover:text-[color:var(--text-secondary)]",
                )}
                style={active ? { borderColor: `${meta.color}44` } : undefined}
              >
                <span
                  aria-hidden
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: meta.color }}
                />
                {getMemoryTypeLabel(type.value, t)}
                <span className="font-mono text-[10.5px] text-[color:var(--text-quaternary)]">
                  {type.count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <span className="mb-2 block font-mono text-[10.5px] uppercase tracking-[0.12em] text-[color:var(--text-quaternary)]">
          {t("memory.map.visibleConnections", { defaultValue: "Conexões" })}
        </span>
        <div className="grid grid-cols-3 gap-1">
          {edgeControls.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => onToggleEdge(item.key)}
              className={cn(
                "flex h-8 items-center justify-center rounded-[var(--radius-panel-sm)] border text-[0.75rem] transition-colors",
                edgeVisibility[item.key]
                  ? "border-[color:var(--border-subtle)] bg-[color:var(--panel)] text-[color:var(--text-primary)]"
                  : "border-[color:var(--border-subtle)] bg-transparent text-[color:var(--text-quaternary)] hover:text-[color:var(--text-secondary)]",
              )}
              aria-pressed={edgeVisibility[item.key]}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MemoryPageContent() {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const defaultBotId = agents[0]?.id ?? "";
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [activeBotId, setActiveBotId] = useState(defaultBotId);
  const [data, setData] = useState<MemoryMapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [userId, setUserId] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<MemoryTypeKey[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [edgeVisibility, setEdgeVisibility] = useState<EdgeVisibility>(DEFAULT_EDGE_VISIBILITY);

  const activeControllerRef = useRef<AbortController | null>(null);
  const requestVersionRef = useRef(0);
  const dataRef = useRef<MemoryMapResponse | null>(null);

  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const activeView: MemoryView =
    searchParams.get("view") === "curation" ? "curation" : "map";

  useEffect(() => {
    if (!defaultBotId) return;
    setActiveBotId((current) => (current ? current : defaultBotId));
  }, [defaultBotId]);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  const fetchData = useCallback(
    async ({ background = false }: { background?: boolean } = {}) => {
      if (!activeBotId) {
        setData(null);
        setLoading(false);
        setError(null);
        return;
      }

      const requestId = requestVersionRef.current + 1;
      requestVersionRef.current = requestId;
      activeControllerRef.current?.abort();

      const controller = new AbortController();
      activeControllerRef.current = controller;

      if (!background || !dataRef.current) setLoading(true);
      if (background && dataRef.current) setRefreshing(true);
      if (!background) setError(null);

      try {
        const payload = await fetchMemoryMap(activeBotId, {
          days,
          includeInactive,
          limit: 160,
          userId,
          sessionId,
          signal: controller.signal,
        });
        if (controller.signal.aborted || requestVersionRef.current !== requestId) return;
        setError(null);
        setData(payload);
      } catch (err: unknown) {
        if (controller.signal.aborted || requestVersionRef.current !== requestId) return;
        const message =
          err instanceof Error
            ? err.message
            : t("memory.map.fallbackLoadError", { defaultValue: "Falha ao carregar memórias" });
        if (!dataRef.current) {
          setError(message);
          setData(null);
        }
      } finally {
        if (requestVersionRef.current === requestId) {
          if (activeControllerRef.current === controller) activeControllerRef.current = null;
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [activeBotId, days, includeInactive, sessionId, t, userId],
  );

  useEffect(() => {
    if (activeView !== "map") {
      return () => {
        activeControllerRef.current?.abort();
      };
    }
    void fetchData();
    const interval = window.setInterval(() => {
      void fetchData({ background: true });
    }, 45_000);
    return () => {
      window.clearInterval(interval);
      activeControllerRef.current?.abort();
    };
  }, [activeView, fetchData]);

  useEffect(() => {
    if (!data) return;
    const incoming = data.filters.types.map((type) => type.value);
    setSelectedTypes((current) => {
      if (current.length === 0) return incoming;
      const intersection = current.filter((value) => incoming.includes(value));
      return intersection.length > 0 ? intersection : incoming;
    });
  }, [data]);

  useEffect(() => {
    if (!data || userId == null) return;
    if (!data.filters.users.some((user) => user.user_id === userId)) setUserId(null);
  }, [data, userId]);

  useEffect(() => {
    if (!data || !sessionId) return;
    if (!data.filters.sessions.some((session) => session.session_id === sessionId)) {
      setSessionId(null);
    }
  }, [data, sessionId]);

  const toggleType = useCallback((type: MemoryTypeKey) => {
    setSelectedTypes((current) =>
      current.includes(type) ? current.filter((value) => value !== type) : [...current, type],
    );
  }, []);

  const toggleEdge = useCallback((key: keyof EdgeVisibility) => {
    setEdgeVisibility((current) => ({ ...current, [key]: !current[key] }));
  }, []);

  const resetFilters = useCallback(() => {
    setSearch("");
    setUserId(null);
    setSessionId(null);
    setDays(30);
    setIncludeInactive(false);
    setEdgeVisibility(DEFAULT_EDGE_VISIBILITY);
    setSelectedTypes(data?.filters.types.map((type) => type.value) ?? []);
  }, [data]);

  const visibleGraph = useMemo(() => {
    if (!data) {
      return { nodes: [] as MemoryNode[], edges: [] as MemoryGraphEdge[] };
    }

    const allTypesSelected =
      selectedTypes.length === 0 || selectedTypes.length === data.filters.types.length;
    const allowedTypes = new Set(selectedTypes);
    const visibleIds = new Set<string>();

    const memoryNodes = data.nodes.filter(
      (node): node is MemoryGraphNode => node.kind === "memory",
    );
    const learningNodes = data.nodes.filter(
      (node): node is MemoryLearningNode => node.kind === "learning",
    );

    memoryNodes.forEach((node) => {
      const matchesType = allTypesSelected || allowedTypes.has(node.memory_type);
      const haystack = [
        node.content,
        node.title,
        node.source_query_preview ?? "",
        node.source_query_text ?? "",
      ]
        .join(" ")
        .toLowerCase();
      const matchesSearch = deferredSearch.length === 0 || haystack.includes(deferredSearch);
      if (matchesType && matchesSearch) visibleIds.add(node.id);
    });

    learningNodes.forEach((node) => {
      const learningMatches =
        deferredSearch.length > 0 &&
        `${node.title} ${node.summary}`.toLowerCase().includes(deferredSearch);
      const hasVisibleMember = node.member_ids.some((memberId) => visibleIds.has(memberId));
      if (learningMatches) {
        node.member_ids.forEach((memberId) => visibleIds.add(memberId));
      }
      if (learningMatches || hasVisibleMember || deferredSearch.length === 0) {
        visibleIds.add(node.id);
      }
    });

    const nodes = data.nodes.filter((node) => {
      if (node.kind === "memory") return visibleIds.has(node.id);
      return visibleIds.has(node.id) && node.member_ids.some((memberId) => visibleIds.has(memberId));
    });

    const edges = data.edges.filter((edge) => {
      const endpointsVisible = visibleIds.has(edge.source) && visibleIds.has(edge.target);
      if (!endpointsVisible) return false;
      if (edge.type === "learning") return true;
      return edgeVisibility[edge.type];
    });

    return { nodes, edges };
  }, [data, deferredSearch, edgeVisibility, selectedTypes]);

  useEffect(() => {
    if (selectedNodeId && !visibleGraph.nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [selectedNodeId, visibleGraph.nodes]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (search.trim()) count += 1;
    if (userId != null) count += 1;
    if (sessionId) count += 1;
    if (days !== 30) count += 1;
    if (includeInactive) count += 1;
    const totalTypes = data?.filters.types.length ?? 0;
    if (totalTypes > 0 && selectedTypes.length > 0 && selectedTypes.length < totalTypes) count += 1;
    if (!edgeVisibility.semantic || !edgeVisibility.session || !edgeVisibility.source) count += 1;
    return count;
  }, [data, days, edgeVisibility, includeInactive, search, selectedTypes.length, sessionId, userId]);

  const setActiveView = useCallback(
    (nextView: MemoryView) => {
      const params = new URLSearchParams(searchParams.toString());
      if (nextView === "curation") params.set("view", "curation");
      else params.delete("view");
      const query = params.toString();
      startTransition(() => {
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
      });
      if (nextView === "curation") setFiltersOpen(false);
    },
    [pathname, router, searchParams],
  );

  const selectedNode: MemoryNode | null = selectedNodeId
    ? visibleGraph.nodes.find((node) => node.id === selectedNodeId) ?? null
    : null;

  const relatedNodes = useMemo<MemoryNode[]>(() => {
    if (!selectedNodeId || !data) return [];
    const neighborIds = new Set<string>();
    data.edges.forEach((edge) => {
      if (edge.source === selectedNodeId) neighborIds.add(edge.target);
      if (edge.target === selectedNodeId) neighborIds.add(edge.source);
    });
    return data.nodes.filter((node) => neighborIds.has(node.id));
  }, [data, selectedNodeId]);

  const relatedEdges = useMemo<MemoryGraphEdge[]>(() => {
    if (!selectedNodeId || !data) return [];
    return data.edges.filter(
      (edge) => edge.source === selectedNodeId || edge.target === selectedNodeId,
    );
  }, [data, selectedNodeId]);

  const handleSelectNode = useCallback((nodeId: string | null) => {
    startTransition(() => {
      setSelectedNodeId(nodeId);
    });
  }, []);

  const handleRequestSearchFocus = useCallback(() => {
    setFiltersOpen(true);
    window.requestAnimationFrame(() => {
      searchInputRef.current?.focus();
    });
  }, []);

  const metricItems = useMemo<
    Array<{ label: string; value: number; tone: MetricTone }>
  >(() => {
    if (!data) return [];
    const memoryCount = visibleGraph.nodes.filter((node) => node.kind === "memory").length;
    const clusterCount = new Set(
      visibleGraph.nodes.filter((n) => n.cluster_id).map((n) => n.cluster_id),
    ).size;
    return [
      {
        label: t("memory.health.active", { defaultValue: "Ativas" }),
        value: memoryCount,
        tone: "neutral",
      },
      {
        label: t("memory.health.semanticEdges", { defaultValue: "Sinapses" }),
        value: visibleGraph.edges.filter((edge) => edge.type === "semantic").length,
        tone: "neutral",
      },
      {
        label: t("memory.map.clusters", { defaultValue: "Clusters" }),
        value: clusterCount,
        tone: "neutral",
      },
      {
        label: t("memory.health.expiring", { defaultValue: "Expirando" }),
        value: data.stats.expiring_soon,
        tone: data.stats.expiring_soon > 0 ? "warning" : "neutral",
      },
    ];
  }, [data, t, visibleGraph.edges, visibleGraph.nodes]);

  const showMap = activeView === "map";
  const showEmpty = showMap && !error && data && data.stats.total_memories === 0 && !loading;
  const showError = showMap && !!error;
  const showInitialLoading = showMap && loading && !data;
  const showCanvas = showMap && data && data.stats.total_memories > 0;

  const controlsRow = (
    <div className="flex flex-wrap items-center gap-2">
      <AgentSwitcher
        activeBotId={activeBotId}
        onAgentChange={(agentId) => {
          setActiveBotId(agentId ?? defaultBotId);
          setSelectedNodeId(null);
          setSearch("");
          setSessionId(null);
          setUserId(null);
          setSelectedTypes([]);
          setFiltersOpen(false);
        }}
        showAll={false}
        singleRow
        className="agent-switcher--compact"
      />
      <SoftTabs
        items={[
          { id: "map", label: t("memory.views.map", { defaultValue: "Mapa" }) },
          { id: "curation", label: t("memory.views.curation", { defaultValue: "Curadoria" }) },
        ]}
        value={activeView}
        onChange={(id) => setActiveView(id as "map" | "curation")}
        ariaLabel={t("memory.map.toggleViewAria", { defaultValue: "Alternar visão" })}
      />
      {showMap && data ? (
        <div className="ml-auto flex items-center gap-2">
          {metricItems.length > 0 ? (
            <div className="hidden items-center gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] px-3 py-1.5 md:flex">
              {metricItems.map((item) => (
                <div key={item.label} className="flex items-baseline gap-1.5">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--text-quaternary)]">
                    {item.label}
                  </span>
                  <span
                    className={cn(
                      "font-mono text-[12px] font-medium tabular-nums text-[color:var(--text-primary)]",
                      item.tone === "warning" && "text-[color:var(--tone-warning-dot)]",
                    )}
                  >
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
          <Popover open={filtersOpen} onOpenChange={setFiltersOpen}>
            <PopoverTrigger asChild>
              <Button variant="secondary" size="sm">
                <SlidersHorizontal className="icon-xs" strokeWidth={1.75} />
                {t("common.filters", { defaultValue: "Filtros" })}
                {activeFilterCount > 0 ? (
                  <span className="ml-1 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[color:var(--accent-muted)] px-1 font-mono text-[10.5px] text-[color:var(--accent)]">
                    {activeFilterCount}
                  </span>
                ) : null}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="p-0">
              <MemoryFiltersPanel
                data={data}
                search={search}
                onSearchChange={setSearch}
                userId={userId}
                onUserChange={setUserId}
                sessionId={sessionId}
                onSessionChange={setSessionId}
                days={days}
                onDaysChange={setDays}
                includeInactive={includeInactive}
                onIncludeInactiveChange={setIncludeInactive}
                selectedTypes={selectedTypes}
                onToggleType={toggleType}
                edgeVisibility={edgeVisibility}
                onToggleEdge={toggleEdge}
                onReset={resetFilters}
                searchInputRef={searchInputRef}
              />
            </PopoverContent>
          </Popover>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void fetchData()}
            aria-label={t("memory.map.refreshAria", { defaultValue: "Atualizar" })}
          >
            <RefreshCcw
              className={cn("icon-xs", refreshing && "animate-spin")}
              strokeWidth={1.75}
            />
          </Button>
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="flex h-[calc(100dvh-var(--shell-topbar-height)-2rem)] flex-col gap-3">
      {controlsRow}

      {activeView === "curation" ? (
        <div className="flex-1 overflow-auto">
          <MemoryCurationWorkspace activeBotId={activeBotId} />
        </div>
      ) : showError ? (
        <div className="flex flex-1 items-center justify-center rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] p-8 text-center">
          <div>
            <p className="text-[0.9375rem] font-medium text-[color:var(--text-primary)]">
              {t("memory.map.unavailableTitle", { defaultValue: "Mapa indisponível" })}
            </p>
            <p className="mt-2 text-[0.8125rem] leading-6 text-[color:var(--text-tertiary)]">
              {error}
            </p>
          </div>
        </div>
      ) : showInitialLoading ? (
        <div className="flex-1 animate-pulse rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]" />
      ) : !activeBotId ? (
        <div className="flex flex-1 items-center justify-center rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]">
          <PageEmptyState
            icon={BrainCircuit}
            title={t("memory.page.noAgentsTitle", { defaultValue: "Sem agentes disponíveis" })}
            description={t("memory.page.noAgentsDescription", {
              defaultValue: "Crie ou publique ao menos um agente antes de abrir o mapa.",
            })}
          />
        </div>
      ) : showEmpty ? (
        <MemoryEmptyStateCard />
      ) : showCanvas ? (
        <div className="relative flex-1">
          <MemoryGraphCanvas
            nodes={visibleGraph.nodes}
            edges={visibleGraph.edges}
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
            onRequestSearchFocus={handleRequestSearchFocus}
          />
          <MemoryInspector
            open={selectedNode != null}
            onOpenChange={(open) => {
              if (!open) handleSelectNode(null);
            }}
            node={selectedNode}
            relatedNodes={relatedNodes}
            relatedEdges={relatedEdges}
            semanticStatus={data?.semantic_status ?? "missing"}
            onFocusNode={(nodeId) => handleSelectNode(nodeId)}
          />
        </div>
      ) : null}
    </div>
  );
}

export default function MemoryPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="h-16 animate-pulse rounded-[var(--radius-panel)] bg-[color:var(--panel-soft)]" />
          <div className="min-h-[480px] animate-pulse rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]" />
        </div>
      }
    >
      <MemoryPageContent />
    </Suspense>
  );
}
