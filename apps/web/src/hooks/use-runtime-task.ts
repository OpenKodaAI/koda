"use client";

import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRuntimeQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { parseResponseError } from "@/lib/http-client";
import { queryKeys } from "@/lib/query/keys";
import type {
  RuntimeEvent,
  RuntimeMutationResult,
  RuntimeTaskBundle,
} from "@/lib/runtime-types";
import { STREAM_ERROR_EVENT, STREAM_REJECTED_RETRY_MS } from "@/lib/sse";

function mergeEvents(current: RuntimeEvent[], incoming: RuntimeEvent[]) {
  const bySeq = new Map<number, RuntimeEvent>();

  [...current, ...incoming].forEach((item) => {
    if (typeof item.seq === "number") {
      bySeq.set(item.seq, item);
    }
  });

  return Array.from(bySeq.values()).sort((left, right) => left.seq - right.seq);
}

async function readJson<T>(response: Response) {
  return (await response.json()) as T;
}

interface UseRuntimeTaskResult {
  bundle: RuntimeTaskBundle | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  connected: boolean;
  refresh: () => Promise<void>;
  mutate: (
    resourcePath: string,
    options?: { searchParams?: URLSearchParams; body?: Record<string, unknown> },
  ) => Promise<RuntimeMutationResult | Record<string, unknown>>;
  fetchResource: <T>(
    resourcePath: string,
    searchParams?: URLSearchParams,
  ) => Promise<T>;
}

export function useRuntimeTask(
  agentId: string,
  taskId: number,
): UseRuntimeTaskResult {
  const { t } = useAppI18n();
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const lastSeqRef = useRef(0);

  // Stable identity: the stream effect below depends on it and would otherwise
  // reopen the EventSource on every render.
  const taskQueryKey = useMemo(
    () => queryKeys.runtime.task(agentId, taskId),
    [agentId, taskId],
  );

  const fetchBundle = useCallback(
    async (signal?: AbortSignal) => {
      const response = await fetch(
        `/api/runtime/agents/${agentId}/tasks/${taskId}`,
        { cache: "no-store", signal },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            t("generated.runtime.nao_foi_possivel_carregar_a_task_de_runtime_d8abe510"),
          ),
        );
      }

      const payload = await readJson<RuntimeTaskBundle>(response);
      lastSeqRef.current =
        payload.events.at(-1)?.seq ?? lastSeqRef.current;
      return payload;
    },
    [agentId, taskId, t],
  );

  const taskQuery = useRuntimeQuery<RuntimeTaskBundle>({
    queryKey: taskQueryKey,
    enabled: Boolean(agentId && taskId),
    refetchInterval: 18_000,
    queryFn: async ({ signal }) => fetchBundle(signal),
  });

  const stableBundleQuery = useStableQueryData({
    data: taskQuery.data,
    resetKey: taskQueryKey,
    isPending: taskQuery.isPending,
    isFetching: taskQuery.isFetching,
    error: taskQuery.error,
  });
  const bundle = stableBundleQuery.data ?? null;

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: taskQueryKey });
  }, [queryClient, taskQueryKey]);

  const fetchResource = useCallback(
    async <T,>(
      resourcePath: string,
      searchParams?: URLSearchParams,
    ) => {
      const suffix = searchParams?.toString()
        ? `?${searchParams.toString()}`
        : "";
      const response = await fetch(
        `/api/runtime/agents/${agentId}/tasks/${taskId}/${resourcePath}${suffix}`,
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            t("generated.runtime.falha_ao_carregar_resourcepath_d14f961f", { resourcePath }),
          ),
        );
      }

      return readJson<T>(response);
    },
    [agentId, taskId, t],
  );

  const mutate = useCallback(
    async (
      resourcePath: string,
      options?: {
        searchParams?: URLSearchParams;
        body?: Record<string, unknown>;
      },
    ): Promise<RuntimeMutationResult | Record<string, unknown>> => {
      const suffix = options?.searchParams?.toString()
        ? `?${options.searchParams.toString()}`
        : "";
      const fetchInit: RequestInit = { method: "POST" };
      if (options?.body) {
        fetchInit.headers = { "Content-Type": "application/json" };
        fetchInit.body = JSON.stringify(options.body);
      }
      const response = await fetch(
        `/api/runtime/agents/${agentId}/tasks/${taskId}/${resourcePath}${suffix}`,
        fetchInit,
      );

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          payload?.error ||
            t("generated.runtime.falha_ao_executar_resourcepath_82d4b5c8", { resourcePath }),
        );
      }

      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      return (payload ?? {}) as RuntimeMutationResult | Record<string, unknown>;
    },
    [agentId, queryClient, taskId, taskQueryKey, t],
  );

  useEffect(() => {
    let disposed = false;
    let reconnectTimer: number | null = null;
    // The latest connection; reconnects replace it, and cleanup must close it.
    let eventSource: EventSource | null = null;

    const connect = () => {
      if (disposed) return;
      const es = new EventSource(
        `/api/runtime/agents/${agentId}/stream?task_id=${taskId}&after_seq=${lastSeqRef.current}`,
      );
      eventSource = es;

      const reconnectAfter = (delayMs: number) => {
        setConnected(false);
        es.close();
        if (disposed) return;
        if (reconnectTimer) window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, delayMs);
      };

      es.onopen = () => {
        setConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as RuntimeEvent;
          if (typeof payload.seq === "number") {
            lastSeqRef.current = Math.max(lastSeqRef.current, payload.seq);
          }

          // Apply event directly to cache instead of scheduling HTTP refetch.
          startTransition(() => {
            queryClient.setQueryData(
              taskQueryKey,
              (current: RuntimeTaskBundle | undefined) =>
                current
                  ? {
                      ...current,
                      events: mergeEvents(current.events, [
                        { ...payload, agentId },
                      ]),
                    }
                  : current,
            );
          });
        } catch {
          // Ignore malformed stream events.
        }
      };

      // The runtime rejected this request: retry only after a long delay
      // instead of every few seconds; the bundle query keeps polling.
      es.addEventListener(STREAM_ERROR_EVENT, () => {
        reconnectAfter(STREAM_REJECTED_RETRY_MS);
      });

      es.onerror = () => {
        reconnectAfter(3000);
      };
    };

    connect();

    return () => {
      disposed = true;
      eventSource?.close();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
    };
  }, [agentId, queryClient, taskId, taskQueryKey]);

  return {
    bundle,
    loading: stableBundleQuery.initialLoading,
    refreshing: stableBundleQuery.refreshing,
    error: stableBundleQuery.showBlockingError ? taskQuery.error?.message ?? null : null,
    connected,
    refresh,
    mutate,
    fetchResource,
  };
}
