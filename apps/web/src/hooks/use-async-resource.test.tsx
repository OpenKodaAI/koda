import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAsyncResource } from "@/hooks/use-async-resource";

describe("useAsyncResource", () => {
  it("loads data and exposes the first-load state", async () => {
    const fetcher = vi.fn(async () => ({ count: 1 }));

    const { result } = renderHook(() =>
      useAsyncResource({
        fetcher,
      }),
    );

    expect(result.current.initialLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 1 });
    });

    expect(result.current.initialLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("preserves previous data when a background refresh fails", async () => {
    const fetcher = vi
      .fn<(_: AbortSignal) => Promise<{ count: number }>>()
      .mockResolvedValueOnce({ count: 1 })
      .mockRejectedValueOnce(new Error("background failed"));

    const { result } = renderHook(() =>
      useAsyncResource({
        fetcher,
      }),
    );

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 1 });
    });

    await act(async () => {
      await result.current.refresh({ background: true, preserveError: true });
    });

    expect(result.current.data).toEqual({ count: 1 });
    expect(result.current.error).toBeNull();
  });
});
