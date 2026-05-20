import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { usePrefetchRouteData } from "@/hooks/use-prefetch-route-data";
import { DASHBOARD_PAGE_SIZE } from "@/lib/pagination";
import { queryKeys } from "@/lib/query/keys";

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider initialLanguage="en-US">{children}</I18nProvider>
      </QueryClientProvider>
    );
  };
}

describe("usePrefetchRouteData", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefetches dashboard list routes into the paginated cache key", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [],
          page: {
            limit: DASHBOARD_PAGE_SIZE,
            offset: 0,
            returned: 0,
            next_offset: null,
            has_more: false,
            total: null,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => usePrefetchRouteData(), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current("/executions");
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const requestUrl = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://localhost");
    expect(requestUrl.pathname).toBe("/api/control-plane/dashboard/executions");
    expect(requestUrl.searchParams.get("paged")).toBe("1");
    expect(requestUrl.searchParams.get("limit")).toBe(String(DASHBOARD_PAGE_SIZE));
    expect(requestUrl.searchParams.get("offset")).toBe("0");

    await waitFor(() => {
      expect(
        queryClient.getQueryData(
          queryKeys.dashboard.executionPages({
            agentIds: [],
            status: "",
            search: "",
            limit: DASHBOARD_PAGE_SIZE,
          }),
        ),
      ).toMatchObject({
        pages: [
          {
            items: [],
            page: {
              limit: DASHBOARD_PAGE_SIZE,
              offset: 0,
              returned: 0,
            },
          },
        ],
      });
    });
  });
});
