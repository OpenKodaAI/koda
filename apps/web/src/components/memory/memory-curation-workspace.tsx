"use client";

import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Search } from "lucide-react";
import { MemoryCurationActions } from "@/components/memory/memory-curation-actions";
import { MemoryCurationDetail } from "@/components/memory/memory-curation-detail";
import { MemoryCurationKpis } from "@/components/memory/memory-curation-kpis";
import { MemoryCurationList } from "@/components/memory/memory-curation-list";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getMemoryTypeLabel, getMemoryTypeMeta, MEMORY_TYPE_ORDER } from "@/lib/memory-constants";
import type {
  MemoryClusterReviewDetail,
  MemoryClusterReviewItem,
  MemoryCurationAvailableFilters,
  MemoryCurationOverview,
  MemoryCurationResponse,
  MemoryReviewDetail,
  MemoryReviewItem,
  MemoryReviewStatus,
  MemoryTypeKey,
} from "@/lib/types";
import {
  fetchMemoryCurationDetail,
  fetchMemoryCurationList,
  postMemoryCurationAction,
} from "./memory-dashboard-api";

type ReviewKind = "memory" | "cluster";
type DetailState = MemoryReviewDetail | MemoryClusterReviewDetail | null;
type SelectableItem = MemoryReviewItem | MemoryClusterReviewItem;

type SelectedEntry = {
  agentId: string;
  kind: ReviewKind;
  id: string;
};

function createEmptyOverview(): MemoryCurationOverview {
  return {
    pending_memories: 0,
    pending_clusters: 0,
    expiring_soon: 0,
    discarded_last_7d: 0,
    merged_last_7d: 0,
    approved_last_7d: 0,
  };
}

function createEmptyFilters(): MemoryCurationAvailableFilters {
  return {
    statuses: [
      "pending",
      "approved",
      "merged",
      "discarded",
      "expired",
      "archived",
    ].map((value) => ({
      value: value as MemoryReviewStatus,
      label: value,
      count: 0,
    })),
    types: MEMORY_TYPE_ORDER.map((value) => ({
      value,
      label: value,
      color: getMemoryTypeMeta(value).color,
      count: 0,
    })),
  };
}

function createEmptyResponse(): MemoryCurationResponse {
  return {
    bot_id: "",
    overview: createEmptyOverview(),
    items: [],
    clusters: [],
    available_filters: createEmptyFilters(),
    page: {
      limit: 0,
      offset: 0,
      total: 0,
      has_more: false,
    },
  };
}

function encodeSelection(entry: SelectedEntry) {
  return `${entry.agentId}::${entry.kind}::${entry.id}`;
}

function decodeSelection(value: string): SelectedEntry {
  const [agentId, kind, id] = value.split("::");
  return {
    agentId,
    kind: kind as ReviewKind,
    id,
  };
}

function sortMemoryItems(items: MemoryReviewItem[]) {
  const order: Record<MemoryReviewStatus, number> = {
    pending: 0,
    expired: 1,
    merged: 2,
    approved: 3,
    discarded: 4,
    archived: 5,
  };

  return [...items].sort((left, right) => {
    const statusDiff = order[left.review_status] - order[right.review_status];
    if (statusDiff !== 0) return statusDiff;
    return (
      new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime()
    );
  });
}

function sortClusterItems(items: MemoryClusterReviewItem[]) {
  const order: Record<MemoryReviewStatus, number> = {
    pending: 0,
    expired: 1,
    merged: 2,
    approved: 3,
    discarded: 4,
    archived: 5,
  };

  return [...items].sort((left, right) => {
    const statusDiff = order[left.review_status] - order[right.review_status];
    if (statusDiff !== 0) return statusDiff;
    return (
      new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime()
    );
  });
}

function getSelectableId(item: SelectableItem) {
  return "memory_id" in item ? String(item.memory_id) : item.cluster_id;
}

export function MemoryCurationWorkspace({
  activeBotId,
}: {
  activeBotId: string;
}) {
  const { t } = useAppI18n();
  const [kind, setKind] = useState<ReviewKind>("memory");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<MemoryReviewStatus | "all">("all");
  const [typeFilter, setTypeFilter] = useState<MemoryTypeKey | "all">("all");
  const [data, setData] = useState<MemoryCurationResponse>(createEmptyResponse);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailState>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<SelectedEntry | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [actionBusy, setActionBusy] = useState(false);

  const deferredSearch = useDeferredValue(search.trim());
  const visibleItems = kind === "memory" ? data.items : data.clusters;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);

    try {
      const payload = await fetchMemoryCurationList(activeBotId, {
        search: deferredSearch,
        status: statusFilter,
        type: typeFilter,
        kind,
        limit: 240,
      });
      setData({
        ...payload,
        items: sortMemoryItems(payload.items),
        clusters: sortClusterItems(payload.clusters),
      });
    } catch (error) {
      setData({
        ...createEmptyResponse(),
        bot_id: activeBotId,
      });
      setLoadError(
        error instanceof Error ? error.message : t("memory.map.fallbackLoadError")
      );
    } finally {
      setLoading(false);
    }
  }, [activeBotId, deferredSearch, kind, statusFilter, t, typeFilter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    setSelectedKeys(new Set());
  }, [kind, activeBotId, statusFilter, typeFilter, deferredSearch]);

  useEffect(() => {
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }, [kind]);

  useEffect(() => {
    if (loading) return;

    if (visibleItems.length === 0) {
      setSelectedItem(null);
      setDetail(null);
      setDetailError(null);
      return;
    }

    const stillExists = selectedItem
      ? visibleItems.some(
          (item) =>
            item.bot_id === selectedItem.agentId && getSelectableId(item) === selectedItem.id
        )
      : false;

    if (stillExists) return;

    const firstItem = visibleItems[0];
    setSelectedItem({
      agentId: firstItem.bot_id,
      kind,
      id: getSelectableId(firstItem),
    });
  }, [kind, loading, selectedItem, visibleItems]);

  useEffect(() => {
    if (!selectedItem) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);

    const run = async () => {
      try {
        const payload = await fetchMemoryCurationDetail(selectedItem.agentId, {
          kind: selectedItem.kind,
          id: selectedItem.id,
        });
        if (!cancelled) setDetail(payload);
      } catch (error) {
        if (!cancelled) {
          setDetail(null);
          setDetailError(
            error instanceof Error ? error.message : t("memory.curation.detailLoadError")
          );
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [selectedItem, t]);

  const selectedCount = selectedKeys.size;

  const handleCheckChange = useCallback(
    (item: SelectableItem, checked: boolean) => {
      const entry: SelectedEntry = {
        agentId: item.bot_id,
        kind,
        id: getSelectableId(item),
      };
      const key = encodeSelection(entry);

      setSelectedKeys((current) => {
        const next = new Set(current);
        if (checked) {
          next.add(key);
        } else {
          next.delete(key);
        }
        return next;
      });
    },
    [kind]
  );

  const runAction = useCallback(
    async (
      action: "approve" | "discard" | "expire" | "archive" | "restore" | "merge",
      options?: { duplicateOfMemoryId?: number | null; targetKeys?: string[] }
    ) => {
      const targetKeys =
        options?.targetKeys ??
        (selectedItem ? [encodeSelection(selectedItem)] : []);

      if (targetKeys.length === 0) return;

      const grouped = new Map<string, string[]>();
      const targetType = decodeSelection(targetKeys[0]).kind;
      targetKeys.forEach((key) => {
        const entry = decodeSelection(key);
        const current = grouped.get(entry.agentId) ?? [];
        current.push(entry.id);
        grouped.set(entry.agentId, current);
      });

      setActionBusy(true);
      try {
        await Promise.all(
          Array.from(grouped.entries()).map(([agentId, targetIds]) =>
            postMemoryCurationAction(agentId, {
                target_type: targetType,
                target_ids: targetIds,
                action,
                duplicate_of_memory_id: options?.duplicateOfMemoryId ?? null,
            })
          )
        );

        setSelectedKeys(new Set());
        await fetchData();
      } catch (error) {
        setDetailError(
          error instanceof Error ? error.message : t("memory.curation.actionError")
        );
      } finally {
        setActionBusy(false);
      }
    },
    [fetchData, selectedItem, t]
  );

  const typeOptions = useMemo(
    () => data.available_filters.types.filter((entry) => entry.count > 0 || entry.value === typeFilter),
    [data.available_filters.types, typeFilter]
  );

  const statusOptions = useMemo(
    () =>
      data.available_filters.statuses.filter(
        (entry) => entry.count > 0 || entry.value === statusFilter
      ),
    [data.available_filters.statuses, statusFilter]
  );

  const getStatusLabel = useCallback(
    (status: MemoryReviewStatus) =>
      t(`memory.curation.status.${status}`, {
        defaultValue: status,
      }),
    [t]
  );

  const listTitle = kind === "memory" ? t("memory.curation.memories") : t("memory.curation.clustersAndLearning");
  const listSubtitle =
    kind === "memory"
      ? `${visibleItems.length} · ${t("memory.curation.pendingCount", { count: data.overview.pending_memories })}`
      : `${visibleItems.length} · ${t("memory.curation.pendingCount", { count: data.overview.pending_clusters })}`;

  return (
    <div className="animate-in flex min-h-0 flex-1 flex-col gap-3">
      <section className="glass-card-sm px-4 py-3.5 sm:px-5">
        <div className="grid gap-3 xl:grid-cols-[12.5rem_12.5rem_13.5rem_minmax(0,1fr)] xl:items-end">
          <div className="min-w-0">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("memory.curation.mode")}
            </span>
            <SoftTabs
              ariaLabel={t("memory.curation.mode")}
              value={kind}
              onChange={(id) => setKind(id as ReviewKind)}
              items={[
                { id: "memory", label: t("memory.curation.memories") },
                { id: "cluster", label: t("memory.curation.clusters") },
              ]}
            />
          </div>

          <label className="block min-w-0">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("memory.curation.states")}
            </span>
            <Select
              value={statusFilter}
              onValueChange={(v) =>
                setStatusFilter(v as MemoryReviewStatus | "all")
              }
            >
              <SelectTrigger
                aria-label={t("memory.curation.states")}
               
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("memory.curation.allStates")}</SelectItem>
                {statusOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {getStatusLabel(option.value)} · {option.count}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="block min-w-0">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("memory.curation.type")}
            </span>
            <Select
              value={typeFilter}
              onValueChange={(v) => setTypeFilter(v as MemoryTypeKey | "all")}
            >
              <SelectTrigger
                aria-label={t("memory.curation.type")}
               
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("memory.curation.allTypes")}</SelectItem>
                {typeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {getMemoryTypeLabel(option.value, t)} · {option.count}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="block min-w-0">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("memory.curation.search")}
            </span>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-quaternary)]" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("memory.curation.searchPlaceholder")}
                className="field-shell pl-9 pr-3 text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
              />
            </div>
          </label>
        </div>

        {selectedCount > 0 ? (
          <div className="mt-3 flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-3 xl:flex-row xl:items-center xl:justify-between">
            <p className="text-sm text-[var(--text-secondary)]">
              {t("memory.curation.selectedCount", { count: selectedCount })}
            </p>
            <MemoryCurationActions
              kind={kind}
              busy={actionBusy}
              compact
              selectedCount={selectedCount}
              canMerge={kind === "memory" && selectedCount > 1}
              onAction={(action) => {
                const targetKeys = Array.from(selectedKeys);
                void runAction(action, { targetKeys });
              }}
            />
          </div>
        ) : null}
      </section>

      <MemoryCurationKpis overview={data.overview} />

      {loadError ? (
        <section className="glass-card px-5 py-6">
          <p className="text-lg font-semibold text-[var(--text-primary)]">
            {t("memory.map.unavailableTitle")}
          </p>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            {loadError}
          </p>
          <div className="mt-4">
            <button
              type="button"
              onClick={() => void fetchData()}
              className="button-shell button-shell--primary"
            >
              {t("common.refresh")}
            </button>
          </div>
        </section>
      ) : (
      <div className="glass-card flex min-h-0 flex-1 overflow-hidden">
        <div className="grid min-h-0 flex-1 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,27rem)_minmax(0,1fr)]">
          <MemoryCurationList
            kind={kind}
            items={visibleItems}
            selectedId={selectedItem?.id ?? null}
            selectedBotId={selectedItem?.agentId ?? null}
            checkedKeys={selectedKeys}
            showAgent={false}
            title={listTitle}
            subtitle={listSubtitle}
            loading={loading}
            emptyLabel={
              kind === "memory"
                ? t("memory.curation.noMemoryFound")
                : t("memory.curation.noClusterFound")
            }
            onSelect={(item) =>
              setSelectedItem({
                agentId: item.bot_id,
                kind,
                id: getSelectableId(item),
              })
            }
            onCheckChange={handleCheckChange}
          />

          <MemoryCurationDetail
            key={`${selectedItem?.agentId ?? "none"}:${selectedItem?.kind ?? kind}:${selectedItem?.id ?? "empty"}`}
            kind={kind}
            detail={detail}
            loading={detailLoading}
            error={detailError}
            busy={actionBusy}
            onAction={(action, options) =>
              void runAction(action, {
                targetKeys: selectedItem ? [encodeSelection(selectedItem)] : [],
                duplicateOfMemoryId: options?.duplicateOfMemoryId ?? null,
              })
            }
            onSelectMemory={(memoryId) => {
              setKind("memory");
              setSelectedItem({
                agentId: activeBotId,
                kind: "memory",
                id: String(memoryId),
              });
            }}
          />
        </div>
      </div>
      )}
    </div>
  );
}
