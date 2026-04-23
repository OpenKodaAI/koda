"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useRuntimeQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveAgentSelection } from "@/lib/agent-selection";
import { parseResponseError, readJsonResponse } from "@/lib/http-client";
import type { RuntimeEvent, RuntimeOverview } from "@/lib/runtime-types";

interface UseRuntimeOverviewResult {
  overviews: Record<string, RuntimeOverview>;
  loading: boolean;
  refreshing: boolean;
  connected: Record<string, boolean>;
  error: string | null;
  refreshAgent: (agentId: string) => Promise<void>;
  lastUpdated: number | null;
}

export function useRuntimeOverview(selectedBotIds?: string[]): UseRuntimeOverviewResult {
  const { language } = useAppI18n();
  const { agents } = useAgentCatalog();
  const queryClient = useQueryClient();
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds],
  );
  const [connected, setConnected] = useState<Record<string, boolean>>({});
  const connectedRef = useRef(connected);
  const lastSeqRef = useRef<Record<string, number>>({});
  const didInitialFetchRef = useRef(false);
  const sseDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  const visibleAgentKey = useMemo(() => visibleBotIds.join(","), [visibleBotIds]);
  const visibleAgentIdsRef = useRef(visibleBotIds);
  useEffect(() => {
    visibleAgentIdsRef.current = visibleBotIds;
  }, [visibleBotIds]);

  const fetchAgentOverview = useCallback(
    async (agentId: string, signal?: AbortSignal) => {
      const params = new URLSearchParams({ lang: language });
      const response = await fetch(
        `/api/runtime/agents/${agentId}/overview?${params.toString()}`,
        { cache: "no-store", signal },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            `Erro ao carregar runtime do agent ${agentId}`,
          ),
        );
      }

      return readJsonResponse<RuntimeOverview>(response);
    },
    [language],
  );

  const fetchBatchOverview = useCallback(
    async (agentIds: string[], signal?: AbortSignal) => {
      if (agentIds.length === 0) return {};

      const params = new URLSearchParams({
        lang: language,
        agents: agentIds.join(","),
      });
      const response = await fetch(
        `/api/runtime/agents/overview?${params.toString()}`,
        { cache: "no-store", signal },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            "Erro ao carregar runtime overview em lote",
          ),
        );
      }

      return readJsonResponse<Record<string, RuntimeOverview>>(response);
    },
    [language],
  );

  const overviewQueryKey = useMemo(
    () => ["runtime", "overview-batch", visibleAgentKey, language] as const,
    [visibleAgentKey, language],
  );
  const overviewQueryKeyRef = useRef(overviewQueryKey);
  useEffect(() => {
    overviewQueryKeyRef.current = overviewQueryKey;
  }, [overviewQueryKey]);

  const overviewQuery = useRuntimeQuery<Record<string, RuntimeOverview>>({
    queryKey: overviewQueryKey,
    enabled: visibleBotIds.length > 0,
    refetchInterval: () => {
      const currentConnected = connectedRef.current;
      const currentBotIds = visibleAgentIdsRef.current;
      const streamAgents = currentBotIds.filter((id) => currentConnected[id]);
      const allConnected =
        streamAgents.length > 0 && streamAgents.length === currentBotIds.length;
      // Safety net: keep a slow 60s poll even when all SSE streams are connected
      return allConnected ? 60_000 : 20_000;
    },
    queryFn: async ({ signal }) => fetchBatchOverview(visibleBotIds, signal),
  });

  const overviews = useMemo(
    () => overviewQuery.data ?? {},
    [overviewQuery.data],
  );

  const streamBotIds = useMemo(
    () =>
      visibleBotIds.filter(
        (agentId) => overviews[agentId]?.availability.runtime === "available",
      ),
    [overviews, visibleBotIds],
  );
  const streamKey = streamBotIds.join(",");

  useEffect(() => {
    if (!didInitialFetchRef.current) {
      didInitialFetchRef.current = true;
      return;
    }

    if (visibleBotIds.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: overviewQueryKey });
  }, [language, queryClient, overviewQueryKey, visibleBotIds.length, visibleAgentKey]);

  useEffect(() => {
    let disposed = false;
    const reconnectTimers: number[] = [];
    const sources: EventSource[] = [];
    const activeStreamBotIds = streamKey ? streamKey.split(",") : [];

    if (activeStreamBotIds.length === 0) {
      return () => undefined;
    }

    const scheduleInvalidation = () => {
      if (sseDebounceRef.current) {
        clearTimeout(sseDebounceRef.current);
      }
      sseDebounceRef.current = setTimeout(() => {
        sseDebounceRef.current = null;
        queryClient.invalidateQueries({
          queryKey: overviewQueryKeyRef.current,
        });
      }, 1_000);
    };

    const connectAgent = (agentId: string) => {
      if (disposed) return;
      const es = new EventSource(
        `/api/runtime/agents/${agentId}/stream?after_seq=${lastSeqRef.current[agentId] ?? 0}`,
      );
      sources.push(es);

      es.onopen = () => {
        setConnected((current) => ({ ...current, [agentId]: true }));
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as RuntimeEvent;
          if (typeof payload.seq === "number") {
            lastSeqRef.current[agentId] = Math.max(
              lastSeqRef.current[agentId] ?? 0,
              payload.seq,
            );
          }

          // Debounce SSE-triggered invalidation: multiple events within 1s
          // coalesce into a single refetch via TanStack Query deduplication.
          scheduleInvalidation();
        } catch {
          // Ignore malformed stream events.
        }
      };

      es.onerror = () => {
        setConnected((current) => ({ ...current, [agentId]: false }));
        es.close();
        if (!disposed) {
          reconnectTimers.push(
            window.setTimeout(() => connectAgent(agentId), 3000),
          );
        }
      };
    };

    activeStreamBotIds.forEach((agentId) => connectAgent(agentId));

    return () => {
      disposed = true;
      sources.forEach((source) => source.close());
      reconnectTimers.forEach((timer) => window.clearTimeout(timer));
      if (sseDebounceRef.current) {
        clearTimeout(sseDebounceRef.current);
        sseDebounceRef.current = null;
      }
    };
  }, [queryClient, streamKey]);

  return {
    overviews,
    loading:
      overviewQuery.isLoading ||
      visibleBotIds.some((agentId) => !overviews[agentId]),
    refreshing: overviewQuery.isFetching && !overviewQuery.isLoading,
    connected,
    error: overviewQuery.error?.message ?? null,
    refreshAgent: async (agentId) => {
      const payload = await fetchAgentOverview(agentId);
      queryClient.setQueryData(
        overviewQueryKey,
        (current: Record<string, RuntimeOverview> | undefined) => ({
          ...(current ?? {}),
          [agentId]: payload,
        }),
      );
    },
    lastUpdated: overviewQuery.dataUpdatedAt || null,
  };
}
