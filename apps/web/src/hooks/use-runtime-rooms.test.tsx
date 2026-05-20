import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { useRuntimeRooms } from "@/hooks/use-runtime-rooms";
import type { PaginatedListResponse } from "@/lib/pagination";
import type { RuntimeRoomRow } from "@/lib/runtime-overview-model";

function runtimeRoomPage(
  taskIds: number[],
  page: PaginatedListResponse<RuntimeRoomRow>["page"],
): PaginatedListResponse<RuntimeRoomRow> {
  return {
    items: taskIds.map((taskId) => ({
      agentId: "ATLAS",
      taskId,
      queryText: `Task ${taskId}`,
      source: "queue",
      status: "running",
      phase: "running",
      updatedAt: "2026-05-18T12:00:00.000Z",
      environment: null,
      queue: null,
    })),
    page,
  };
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider initialLanguage="en-US">{children}</I18nProvider>
      </QueryClientProvider>
    );
  };
}

describe("useRuntimeRooms", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("paginates, refreshes only the first page, and reuses cached pages", async () => {
    const responses = [
      runtimeRoomPage([1], {
        limit: 25,
        offset: 0,
        returned: 1,
        next_offset: 25,
        has_more: true,
        total: null,
      }),
      runtimeRoomPage([2], {
        limit: 25,
        offset: 25,
        returned: 1,
        next_offset: null,
        has_more: false,
        total: null,
      }),
      runtimeRoomPage([10], {
        limit: 25,
        offset: 0,
        returned: 1,
        next_offset: 25,
        has_more: true,
        total: null,
      }),
    ];
    const fetchMock = vi.fn(async () => {
      const response = responses.shift();
      return new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = createWrapper(queryClient);

    const { result, unmount } = renderHook(
      () =>
        useRuntimeRooms({
          agentIds: ["ATLAS", "NOVA"],
          status: "all",
          search: "  ",
        }),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current.data?.pages[0]?.items[0]?.taskId).toBe(1);
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages.map((page) => page.items[0]?.taskId)).toEqual([
        1,
        2,
      ]);
    });

    await act(async () => {
      await result.current.refreshFirstPage();
    });

    await waitFor(() => {
      expect(result.current.data?.pages.map((page) => page.items[0]?.taskId)).toEqual([
        10,
        2,
      ]);
    });

    unmount();

    const cached = renderHook(
      () =>
        useRuntimeRooms({
          agentIds: ["ATLAS", "NOVA"],
          status: "all",
          search: "",
        }),
      { wrapper },
    );

    expect(cached.result.current.data?.pages.map((page) => page.items[0]?.taskId)).toEqual([
      10,
      2,
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const requestedOffsets = fetchMock.mock.calls.map(([input]) =>
      new URL(String(input), "http://localhost").searchParams.get("offset"),
    );
    expect(requestedOffsets).toEqual(["0", "25", "0"]);
  });
});
