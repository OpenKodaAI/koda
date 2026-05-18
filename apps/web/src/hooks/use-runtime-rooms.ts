"use client";

import { useCallback, useMemo } from "react";
import {
  type InfiniteData,
  useInfiniteQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { parseResponseError, readJsonResponse } from "@/lib/http-client";
import {
  DASHBOARD_CACHE_GC_MS,
  DASHBOARD_CACHE_STALE_MS,
  emptyPaginatedList,
  type PaginatedListResponse,
} from "@/lib/pagination";
import { queryKeys } from "@/lib/query/keys";
import type { RuntimeRoomFilter, RuntimeRoomRow } from "@/lib/runtime-overview-model";

const RUNTIME_ROOM_PAGE_SIZE = 25;

export function useRuntimeRooms({
  agentIds,
  status,
  search,
}: {
  agentIds: string[];
  status: RuntimeRoomFilter;
  search: string;
}) {
  const { language } = useAppI18n();
  const queryClient = useQueryClient();
  const normalizedSearch = search.trim();
  const queryKey = useMemo(
    () =>
      queryKeys.runtime.rooms({
        agentIds,
        status,
        search: normalizedSearch,
        limit: RUNTIME_ROOM_PAGE_SIZE,
      }),
    [agentIds, normalizedSearch, status],
  );

  const fetchRuntimeRoomsPage = useCallback(
    async ({
      offset,
      signal,
    }: {
      offset: number;
      signal?: AbortSignal;
    }) => {
      const params = new URLSearchParams({
        lang: language,
        agents: agentIds.join(","),
        status,
        limit: String(RUNTIME_ROOM_PAGE_SIZE),
        offset: String(offset),
      });
      if (normalizedSearch) {
        params.set("search", normalizedSearch);
      }
      const response = await fetch(`/api/runtime/agents/rooms?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!response.ok) {
        throw new Error(
          await parseResponseError(response, "Erro ao carregar salas runtime."),
        );
      }
      return readJsonResponse<PaginatedListResponse<RuntimeRoomRow>>(response);
    },
    [agentIds, language, normalizedSearch, status],
  );

  const query = useInfiniteQuery<PaginatedListResponse<RuntimeRoomRow>, Error>({
    queryKey,
    initialPageParam: 0,
    enabled: agentIds.length > 0,
    staleTime: DASHBOARD_CACHE_STALE_MS,
    gcTime: DASHBOARD_CACHE_GC_MS,
    retry: 1,
    refetchOnWindowFocus: false,
    getNextPageParam: (lastPage) =>
      lastPage.page.has_more ? lastPage.page.next_offset : undefined,
    queryFn: async ({ signal, pageParam }) => {
      const offset = typeof pageParam === "number" ? pageParam : 0;
      return fetchRuntimeRoomsPage({ offset, signal });
    },
    placeholderData: (previous) =>
      previous ?? {
        pages: [emptyPaginatedList<RuntimeRoomRow>(RUNTIME_ROOM_PAGE_SIZE, 0)],
        pageParams: [0],
      },
  });

  const refreshFirstPage = useCallback(async () => {
    if (agentIds.length === 0) return;
    const firstPage = await fetchRuntimeRoomsPage({ offset: 0 });
    queryClient.setQueryData<
      InfiniteData<PaginatedListResponse<RuntimeRoomRow>, number>
    >(queryKey, (current) => {
      if (!current) {
        return {
          pages: [firstPage],
          pageParams: [0],
        };
      }
      return {
        ...current,
        pages: [firstPage, ...current.pages.slice(1)],
        pageParams: current.pageParams.length > 0 ? current.pageParams : [0],
      };
    });
  }, [agentIds.length, fetchRuntimeRoomsPage, queryClient, queryKey]);

  return {
    ...query,
    refreshFirstPage,
  };
}
