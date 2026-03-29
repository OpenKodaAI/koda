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
  DatabaseZap,
  RefreshCcw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { PageEmptyState } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  MemoryGraphEdge,
  MemoryGraphNode,
  MemoryLearningNode,
  MemoryMapResponse,
  MemoryTypeKey,
} from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";
import { getMemoryTypeLabel } from "@/lib/memory-constants";
import { fetchMemoryMap } from "@/components/memory/memory-dashboard-api";

const MemoryMapCanvas = dynamic(
  () =>
    import("@/components/memory/memory-map-canvas").then((module) => ({
      default: module.MemoryMapCanvas,
    })),
  {
    loading: () => <div className="glass-card min-h-[480px] animate-pulse sm:min-h-[620px]" />,
  },
);

const MemoryCurationWorkspace = dynamic(
  () =>
    import("@/components/memory/memory-curation-workspace").then((module) => ({
      default: module.MemoryCurationWorkspace,
    })),
  {
    loading: () => <div className="glass-card min-h-[420px] animate-pulse sm:min-h-[560px]" />,
  },
);

type MemoryNode = MemoryGraphNode | MemoryLearningNode;
type EdgeVisibility = {
  semantic: boolean;
  session: boolean;
  source: boolean;
};
type MemoryView = "map" | "curation";

const DAY_OPTIONS = [7, 30, 90] as const;
function MemoryEmptyState() {
  const { t } = useAppI18n();
  return (
    <div className="glass-card min-h-[420px] px-6 py-10 sm:min-h-[560px]">
      <PageEmptyState
        title={t("memory.empty.title")}
        description={t("memory.empty.description")}
        visual={
          <div className="relative mb-2 flex h-24 w-24 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)]">
            <div className="absolute inset-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)]" />
            <svg width="54" height="54" viewBox="0 0 54 54" fill="none" className="relative">
              <circle cx="27" cy="27" r="5" fill="rgba(255,255,255,0.92)" />
              <circle cx="14" cy="18" r="3" fill="rgba(200,202,214,0.9)" />
              <circle cx="39" cy="16" r="3" fill="rgba(124,124,146,0.9)" />
              <circle cx="40" cy="38" r="3" fill="rgba(15,15,16,0.96)" />
              <path
                d="M17 19.5L23 24M31 24L36.5 18.5M31 30.5L37 36.5"
                stroke="rgba(255,255,255,0.32)"
                strokeWidth="1.35"
                strokeLinecap="round"
              />
            </svg>
          </div>
        }
      />
    </div>
  );
}

interface MemoryFiltersContentProps {
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
  compact?: boolean;
  showIntro?: boolean;
  hidePrimaryFields?: boolean;
  hideTimeWindow?: boolean;
}

function MemoryFiltersContent({
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
  compact = false,
  showIntro = true,
  hidePrimaryFields = false,
  hideTimeWindow = false,
}: MemoryFiltersContentProps) {
  const { t } = useAppI18n();
  const edgeControls: Array<{ key: keyof EdgeVisibility; label: string }> = [
    { key: "semantic", label: t("memory.filters.edges.semantic") },
    { key: "session", label: t("memory.filters.edges.session") },
    { key: "source", label: t("memory.filters.edges.source") },
  ];
  return (
    <div className={cn("space-y-4", compact && "space-y-4")}>
      {showIntro && (
        <div>
          <p className="eyebrow">{t("memory.filters.title")}</p>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            {t("memory.filters.intro")}
          </p>
        </div>
      )}

      {!hidePrimaryFields && (
        <>
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("memory.filters.search")}
            </span>
            <div className="relative">
              <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-quaternary)]" />
              <input
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={t("memory.filters.searchPlaceholder")}
                className="field-shell py-3 pl-11 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
              />
            </div>
          </label>

          <div className={cn("grid gap-3", compact && "sm:grid-cols-2")}>
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("memory.filters.user")}
              </span>
              <select
                value={userId ?? ""}
                onChange={(event) => onUserChange(event.target.value ? Number(event.target.value) : null)}
                className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
              >
                <option value="">{t("common.allUsers")}</option>
                {data.filters.users.map((user) => (
                  <option key={user.user_id} value={user.user_id}>
                    {user.label} · {user.count}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("memory.filters.session")}
            </span>
              <select
                value={sessionId ?? ""}
                onChange={(event) => onSessionChange(event.target.value || null)}
                className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
              >
                <option value="">{t("common.allSessions")}</option>
                {data.filters.sessions.map((session) => (
                  <option key={session.session_id} value={session.session_id}>
                    {session.label} · {session.count}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}

      {!hideTimeWindow && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
            {t("memory.filters.timeWindow")}
          </p>
          <div className="segmented-control segmented-control--full">
            {DAY_OPTIONS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => onDaysChange(value)}
                className={cn("segmented-control__option", days === value && "is-active")}
                aria-pressed={days === value}
              >
                {value}d
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => onIncludeInactiveChange(!includeInactive)}
        className={cn(
          "button-shell button-shell--secondary w-full justify-between text-sm",
          includeInactive && "button-shell--primary"
        )}
      >
        <span>{t("memory.filters.includeInactive")}</span>
        <span className="chip">{includeInactive ? t("common.on") : t("common.off")}</span>
      </button>

      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
          {t("memory.map.filterTitle")}
        </p>
        <div className="flex flex-wrap gap-2">
          {data.filters.types.map((type) => {
            const active = selectedTypes.includes(type.value);
            return (
              <button
                key={type.value}
                type="button"
                onClick={() => onToggleType(type.value)}
                className={cn(
                  "button-pill",
                  active && "is-active"
                )}
                style={
                  active
                    ? {
                        borderColor: `${type.color}44`,
                        color: "var(--text-primary)",
                        boxShadow: `0 16px 32px ${type.color}1c`,
                      }
                    : undefined
                }
              >
                {getMemoryTypeLabel(type.value, t)} · {type.count}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
          {t("memory.map.visibleConnections")}
        </p>
        <div className={cn("space-y-2", compact && "grid gap-2 space-y-0 sm:grid-cols-3")}>
          {edgeControls.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => onToggleEdge(item.key)}
              className={cn(
                "button-shell button-shell--secondary w-full justify-between text-sm",
                edgeVisibility[item.key] && "button-shell--primary"
              )}
            >
              {item.label}
              <span className="chip">{edgeVisibility[item.key] ? t("memory.map.visible") : t("memory.map.hidden")}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MemoryPageContent() {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const defaultBotId = bots[0]?.id ?? "";
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
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
  const [edgeVisibility, setEdgeVisibility] = useState<EdgeVisibility>({
    semantic: true,
    session: true,
    source: true,
  });
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

  const fetchData = useCallback(async ({ background = false }: { background?: boolean } = {}) => {
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

    if (!background || !dataRef.current) {
      setLoading(true);
    }
    if (background && dataRef.current) {
      setRefreshing(true);
    }

    if (!background) {
      setError(null);
    }

    try {
      const payload = await fetchMemoryMap(activeBotId, {
        days,
        includeInactive,
        limit: 160,
        userId,
        sessionId,
        signal: controller.signal,
      });
      if (controller.signal.aborted || requestVersionRef.current !== requestId) {
        return;
      }

      setError(null);
      setData(payload);
    } catch (err: unknown) {
      if (controller.signal.aborted || requestVersionRef.current !== requestId) {
        return;
      }

      const message =
        err instanceof Error ? err.message : t("memory.map.fallbackLoadError");

      if (!dataRef.current) {
        setError(message);
        setData(null);
        return;
      }
    } finally {
      if (requestVersionRef.current === requestId) {
        if (activeControllerRef.current === controller) {
          activeControllerRef.current = null;
        }
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [activeBotId, days, includeInactive, sessionId, t, userId]);

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
    if (!data.filters.users.some((user) => user.user_id === userId)) {
      setUserId(null);
    }
  }, [data, userId]);

  useEffect(() => {
    if (!data || !sessionId) return;
    if (!data.filters.sessions.some((session) => session.session_id === sessionId)) {
      setSessionId(null);
    }
  }, [data, sessionId]);

  const toggleType = useCallback((type: MemoryTypeKey) => {
    setSelectedTypes((current) =>
      current.includes(type)
        ? current.filter((value) => value !== type)
        : [...current, type]
    );
  }, []);

  const toggleEdge = useCallback((key: keyof EdgeVisibility) => {
    setEdgeVisibility((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }, []);

  const resetFilters = useCallback(() => {
    setSearch("");
    setUserId(null);
    setSessionId(null);
    setDays(30);
    setIncludeInactive(false);
    setEdgeVisibility({
      semantic: true,
      session: true,
      source: true,
    });
    setSelectedTypes(data?.filters.types.map((type) => type.value) ?? []);
    setFiltersOpen(false);
  }, [data]);

  const visibleGraph = useMemo(() => {
    if (!data) {
      return {
        nodes: [] as MemoryNode[],
        edges: [] as MemoryGraphEdge[],
      };
    }

    const allTypesSelected =
      selectedTypes.length === 0 ||
      selectedTypes.length === data.filters.types.length;

    const allowedTypes = new Set(selectedTypes);
    const visibleIds = new Set<string>();

    const memoryNodes = data.nodes.filter(
      (node): node is MemoryGraphNode => node.kind === "memory"
    );
    const learningNodes = data.nodes.filter(
      (node): node is MemoryLearningNode => node.kind === "learning"
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
      if (matchesType && matchesSearch) {
        visibleIds.add(node.id);
      }
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
      if (node.kind === "memory") {
        return visibleIds.has(node.id);
      }
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
    if (totalTypes > 0 && selectedTypes.length > 0 && selectedTypes.length < totalTypes) {
      count += 1;
    }

    if (!edgeVisibility.semantic || !edgeVisibility.session || !edgeVisibility.source) {
      count += 1;
    }

    return count;
  }, [data, days, edgeVisibility, includeInactive, search, selectedTypes.length, sessionId, userId]);

  const setActiveView = useCallback(
    (nextView: MemoryView) => {
      const params = new URLSearchParams(searchParams.toString());
      if (nextView === "curation") {
        params.set("view", "curation");
      } else {
        params.delete("view");
      }

      const query = params.toString();
      startTransition(() => {
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
      });

      if (nextView === "curation") {
        setFiltersOpen(false);
      }
    },
    [pathname, router, searchParams]
  );

  return (
    <div
      className={cn(
        "flex flex-col gap-4",
        activeView === "curation" &&
          "xl:h-[calc(100dvh-var(--shell-topbar-height)-4.5rem)] xl:overflow-hidden 2xl:h-[calc(100dvh-var(--shell-topbar-height)-5.25rem)]"
      )}
    >
      <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(260px,350px)_minmax(220px,280px)_auto]">
        <div className="min-w-0">
          <BotSwitcher
            activeBotId={activeBotId}
            onBotChange={(botId) => {
              setActiveBotId(botId ?? defaultBotId);
              setSelectedNodeId(null);
              setSearch("");
              setSessionId(null);
              setUserId(null);
              setSelectedTypes([]);
              setFiltersOpen(false);
            }}
            showAll={false}
            singleRow
          />
        </div>

        <div className="min-w-0 self-stretch">
          <div
            className="segmented-control segmented-control--single-row h-full min-h-[44px]"
            role="group"
            aria-label={t("memory.map.toggleViewAria")}
          >
            <button
              type="button"
              onClick={() => setActiveView("map")}
              className={cn(
                "segmented-control__option",
                activeView === "map" && "is-active"
              )}
              aria-pressed={activeView === "map"}
            >
              {t("memory.views.map")}
            </button>
            <button
              type="button"
              onClick={() => setActiveView("curation")}
              className={cn(
                "segmented-control__option",
                activeView === "curation" && "is-active"
              )}
              aria-pressed={activeView === "curation"}
            >
              {t("memory.views.curation")}
            </button>
          </div>
        </div>

        <div className="flex min-h-[44px] items-center justify-start sm:justify-end">
          {activeView === "map" ? (
            <button
              type="button"
              onClick={() => void fetchData()}
              className="button-shell button-shell--primary h-10 px-4 text-sm"
              aria-label={t("memory.map.refreshAria")}
            >
              <RefreshCcw className={cn("h-4 w-4", refreshing && "animate-spin")} />
              <span>{t("common.refresh")}</span>
            </button>
          ) : null}
        </div>
      </div>

      {activeView === "curation" ? (
        <MemoryCurationWorkspace activeBotId={activeBotId} />
      ) : error ? (
        <div className="glass-card p-6">
          <p className="text-lg font-semibold text-[var(--text-primary)]">
            {t("memory.map.unavailableTitle")}
          </p>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{error}</p>
        </div>
      ) : loading && !data ? (
        <div className="space-y-4">
          {/* Controls bar */}
          <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(260px,350px)_minmax(220px,280px)_auto]">
            <div className="min-w-0">
              <div className="skeleton h-11 w-full rounded-xl" />
            </div>
            <div className="min-w-0 self-stretch">
              <div className="skeleton h-11 w-full rounded-xl" />
            </div>
            <div className="flex min-h-[44px] items-center justify-end">
              <div className="skeleton h-10 w-32 rounded-lg" />
            </div>
          </div>

          {/* Filter section */}
          <div className="glass-card min-h-[120px] p-5 sm:p-6" />

          {/* Main content */}
          <div className="glass-card min-h-[420px] p-5 sm:min-h-[560px] sm:p-6" />
        </div>
      ) : !activeBotId || !data ? (
        <div className="glass-card min-h-[420px] px-6 py-10 sm:min-h-[560px]">
          <PageEmptyState
            title={t("memory.page.noBotsTitle", { defaultValue: "No agents available" })}
            description={t("memory.page.noBotsDescription", {
              defaultValue: "Create or publish at least one agent before opening the memory workspace.",
            })}
          />
        </div>
      ) : data && data.stats.total_memories === 0 ? (
        <MemoryEmptyState />
      ) : (
        (() => {
          const currentData = data!;

          return (
            <>
              <div className="space-y-4">
                <section className="glass-card p-5 sm:p-6">
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                      <h2 className="text-[1.42rem] font-semibold tracking-[-0.055em] text-[var(--text-primary)] sm:text-[1.6rem]">
                        {t("memory.map.mapAndFilters")}
                      </h2>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="chip">
                          {t("memory.map.memoryCount", {
                            count: visibleGraph.nodes.filter((node) => node.kind === "memory").length,
                          })}
                        </span>
                        <span className="chip">
                          {t("memory.map.connectionsCount", { count: visibleGraph.edges.length })}
                        </span>
                        {activeFilterCount > 0 && (
                          <span className="chip">
                            {t("memory.map.activeFilters", { count: activeFilterCount })}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_240px_240px]">
                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                          {t("memory.map.searchMap")}
                        </span>
                        <div className="relative">
                          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-quaternary)]" />
                          <input
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder={t("memory.map.searchPlaceholder")}
                            className="field-shell py-3 pl-11 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
                          />
                        </div>
                      </label>

                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                          {t("common.user")}
                        </span>
                        <select
                          value={userId ?? ""}
                          onChange={(event) =>
                            setUserId(event.target.value ? Number(event.target.value) : null)
                          }
                          className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
                        >
                          <option value="">{t("common.allUsers")}</option>
                          {currentData.filters.users.map((user) => (
                            <option key={user.user_id} value={user.user_id}>
                              {user.label} · {user.count}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                          {t("common.session")}
                        </span>
                        <select
                          value={sessionId ?? ""}
                          onChange={(event) => setSessionId(event.target.value || null)}
                          className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
                        >
                          <option value="">{t("common.allSessions")}</option>
                          {currentData.filters.sessions.map((session) => (
                            <option key={session.session_id} value={session.session_id}>
                              {session.label} · {session.count}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-4 xl:flex-row xl:items-end xl:justify-between">
                      <div className="min-w-0">
                        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                          {t("memory.map.timeWindow")}
                        </p>
                        <div className="segmented-control segmented-control--full">
                          {DAY_OPTIONS.map((value) => (
                            <button
                              key={value}
                              type="button"
                              onClick={() => setDays(value)}
                            className={cn("segmented-control__option", days === value && "is-active")}
                            aria-pressed={days === value}
                          >
                              {t("memory.map.days", { count: value })}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                        <button
                          type="button"
                          onClick={() => setIncludeInactive((current) => !current)}
                          className={cn(
                            "button-shell button-shell--secondary justify-between gap-4 px-4 text-sm xl:min-w-[220px]",
                            includeInactive && "button-shell--primary"
                          )}
                        >
                          <span>{t("memory.map.inactiveMemories")}</span>
                          <span className="chip">{includeInactive ? t("common.on") : t("common.off")}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setFiltersOpen((current) => !current)}
                          className="button-shell button-shell--secondary px-4 text-sm text-[var(--text-secondary)]"
                        >
                          <SlidersHorizontal className="h-4 w-4" />
                          {filtersOpen ? t("common.hideRefinements") : t("common.refine")}
                        </button>
                        {activeFilterCount > 0 && (
                          <button
                            type="button"
                            onClick={resetFilters}
                            className="button-shell button-shell--quiet px-4 text-sm"
                          >
                            {t("common.clear")}
                          </button>
                        )}
                      </div>
                    </div>

                    {filtersOpen && (
                      <div className="border-t border-[var(--border-subtle)] pt-4">
                        <MemoryFiltersContent
                          data={currentData}
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
                          compact
                          showIntro={false}
                          hidePrimaryFields
                          hideTimeWindow
                        />
                      </div>
                    )}
                  </div>
                </section>

                <div className="space-y-4">
                  <section className="glass-card overflow-hidden p-0">
                    <MemoryMapCanvas
                      nodes={visibleGraph.nodes}
                      edges={visibleGraph.edges}
                      selectedNodeId={selectedNodeId}
                      storageScope={activeBotId}
                      onSelectNode={(nodeId) =>
                        startTransition(() => {
                          setSelectedNodeId(nodeId);
                        })
                      }
                    />
                  </section>

                  <section className="panel-soft p-5 lg:p-6">
                    <div className="mb-5 flex flex-col gap-4 border-b border-[var(--border-subtle)] pb-5 lg:flex-row lg:items-end lg:justify-between">
                      <div className="flex items-center gap-3">
                        <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)]">
                          <DatabaseZap className="h-4.5 w-4.5 text-[var(--bot-luby)]" />
                        </span>
                        <div>
                          <p className="eyebrow">{t("memory.health.eyebrow")}</p>
                          <h3 className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                            {t("memory.health.title")}
                          </h3>
                        </div>
                      </div>

                      <span className="chip">
                        {currentData.semantic_status === "available"
                          ? t("memory.health.semanticAvailable")
                          : currentData.semantic_status === "fallback"
                            ? t("memory.health.semanticFallback")
                            : t("memory.health.semanticUnavailable")}
                      </span>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.active")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.active_memories}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.inactive")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.inactive_memories}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.learning")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.learning_nodes}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.expiring")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.expiring_soon}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.semanticEdges")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.semantic_edges}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.contextualEdges")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.contextual_edges}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.maintenance")}
                        </p>
                        <p className="mt-2 text-[1.18rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {currentData.stats.maintenance_operations}
                        </p>
                      </div>
                      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                          {t("memory.health.lastMaintenance")}
                        </p>
                        <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-primary)]">
                          {currentData.stats.last_maintenance_at
                            ? formatDateTime(currentData.stats.last_maintenance_at)
                            : t("memory.health.noMaintenance")}
                        </p>
                      </div>
                    </div>
                  </section>
                </div>
              </div>
            </>
          );
        })()
      )}
    </div>
  );
}

export default function MemoryPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="glass-card-sm h-[4.5rem] animate-pulse" />
          <div className="panel-soft min-h-[168px] animate-pulse" />
          <div className="glass-card min-h-[480px] animate-pulse sm:min-h-[620px]" />
          <div className="panel-soft min-h-[220px] animate-pulse" />
        </div>
      }
    >
      <MemoryPageContent />
    </Suspense>
  );
}
