"use client";

import {
  startTransition,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRuntimeQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { parseResponseError } from "@/lib/http-client";
import { queryKeys } from "@/lib/query/keys";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import {
  buildMockRuntimeTaskBundle,
  readMockWorkspaceFile,
  readMockWorkspaceSearch,
  readMockWorkspaceTree,
} from "@/lib/runtime-mocks";
import type {
  RuntimeEvent,
  RuntimeMutationResult,
  RuntimeTaskBundle,
  RuntimeTerminal,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";

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
  options?: { mock?: boolean },
): UseRuntimeTaskResult {
  const { tl } = useAppI18n();
  const { agents } = useAgentCatalog();
  const queryClient = useQueryClient();
  const mock = Boolean(options?.mock);
  const [connected, setConnected] = useState(false);
  const [mockTick, setMockTick] = useState(0);
  const lastSeqRef = useRef(0);

  const taskQueryKey = queryKeys.runtime.task(agentId, taskId);

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
            tl("Não foi possível carregar a task de runtime."),
          ),
        );
      }

      const payload = await readJson<RuntimeTaskBundle>(response);
      lastSeqRef.current =
        payload.events.at(-1)?.seq ?? lastSeqRef.current;
      return payload;
    },
    [agentId, taskId, tl],
  );

  const taskQuery = useRuntimeQuery<RuntimeTaskBundle>({
    queryKey: taskQueryKey,
    enabled: !mock && Boolean(agentId && taskId),
    refetchInterval: 18_000,
    queryFn: async ({ signal }) => fetchBundle(signal),
  });

  useEffect(() => {
    if (!mock) return undefined;
    const timer = window.setInterval(() => setMockTick((current) => current + 1), 1_800);
    return () => window.clearInterval(timer);
  }, [mock]);

  const bundle = mock
    ? buildMockRuntimeTaskBundle(agents, agentId, taskId, mockTick)
    : taskQuery.data ?? null;

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: taskQueryKey });
  }, [queryClient, taskQueryKey]);

  const fetchResource = useCallback(
    async <T,>(
      resourcePath: string,
      searchParams?: URLSearchParams,
    ) => {
      if (mock) {
        if (resourcePath === "terminals") {
          return { items: bundle?.terminals ?? [] } as T;
        }
        if (resourcePath === "workspace/tree") {
          return {
            items: readMockWorkspaceTree(searchParams?.get("path") ?? ""),
          } as T;
        }
        if (resourcePath === "workspace/file") {
          return readMockWorkspaceFile(searchParams?.get("path") ?? "") as T;
        }
        if (resourcePath === "workspace/search") {
          return readMockWorkspaceSearch(searchParams?.get("q") ?? "") as T;
        }
        if (resourcePath === "browser") {
          return { browser: bundle?.browser ?? null } as T;
        }
        return {} as T;
      }

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
            tl("Falha ao carregar {{resourcePath}}", { resourcePath }),
          ),
        );
      }

      return readJson<T>(response);
    },
    [agentId, bundle, mock, taskId, tl],
  );

  const mutate = useCallback(
    async (
      resourcePath: string,
      options?: {
        searchParams?: URLSearchParams;
        body?: Record<string, unknown>;
      },
    ): Promise<RuntimeMutationResult | Record<string, unknown>> => {
      if (mock) {
        setMockTick((current) => current + 1);
        if (resourcePath === "attach/terminal") {
          const terminal = bundle?.terminals.at(-1) as RuntimeTerminal | undefined;
          return {
            ok: true,
            terminal,
            attach: {
              task_id: taskId,
              terminal_id: terminal?.id ?? 1,
              can_write: true,
              status: "mock",
            },
          };
        }
        if (resourcePath === "attach/browser") {
          return { ok: true, browser: bundle?.browser ?? null };
        }
        if (resourcePath === "workspace/file") {
          return readMockWorkspaceFile(
            options?.searchParams?.get("path") ?? "",
          ) as unknown as Record<string, unknown>;
        }
        if (resourcePath === "workspace/tree") {
          return {
            items: readMockWorkspaceTree(options?.searchParams?.get("path") ?? ""),
          } as { items: RuntimeWorkspaceTreeEntry[] };
        }
        return { ok: true, action: resourcePath, task_id: taskId };
      }

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
            tl("Falha ao executar {{resourcePath}}", { resourcePath }),
        );
      }

      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      return (payload ?? {}) as RuntimeMutationResult | Record<string, unknown>;
    },
    [agentId, bundle, mock, queryClient, taskId, taskQueryKey, tl],
  );

  useEffect(() => {
    if (mock) {
      return () => undefined;
    }
    let disposed = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      if (disposed) return;
      const es = new EventSource(
        `/api/runtime/agents/${agentId}/stream?task_id=${taskId}&after_seq=${lastSeqRef.current}`,
      );

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

      es.onerror = () => {
        setConnected(false);
        es.close();
        if (!disposed) {
          reconnectTimer = window.setTimeout(connect, 3000);
        }
      };

      return es;
    };

    const source = connect();

    return () => {
      disposed = true;
      source?.close();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
    };
  }, [agentId, mock, queryClient, taskId, taskQueryKey]);

  return {
    bundle,
    loading: !mock && taskQuery.isLoading && !bundle,
    refreshing: taskQuery.isFetching && !taskQuery.isLoading,
    error: taskQuery.error?.message ?? null,
    connected: mock || connected,
    refresh,
    mutate,
    fetchResource,
  };
}
