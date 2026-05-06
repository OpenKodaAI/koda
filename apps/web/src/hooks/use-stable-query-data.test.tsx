import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useStableQueryData } from "@/hooks/use-stable-query-data";

describe("useStableQueryData", () => {
  it("keeps the last data while a compatible query refreshes", () => {
    const { result, rerender } = renderHook(
      ({ data, isFetching }: { data?: { value: string }; isFetching: boolean }) =>
        useStableQueryData({
          data,
          resetKey: "stable",
          isPending: false,
          isFetching,
        }),
      { initialProps: { data: { value: "ready" }, isFetching: false } },
    );

    expect(result.current.data).toEqual({ value: "ready" });
    rerender({ data: undefined, isFetching: true });

    expect(result.current.data).toEqual({ value: "ready" });
    expect(result.current.refreshing).toBe(true);
    expect(result.current.initialLoading).toBe(false);
  });

  it("clears stale data when the reset key changes", () => {
    const { result, rerender } = renderHook(
      ({ resetKey, data }: { resetKey: string; data?: { id: string } }) =>
        useStableQueryData({
          data,
          resetKey,
          isPending: true,
          isFetching: true,
        }),
      { initialProps: { resetKey: "a", data: { id: "a" } } },
    );

    expect(result.current.data).toEqual({ id: "a" });
    rerender({ resetKey: "b", data: undefined });

    expect(result.current.data).toBeNull();
    expect(result.current.initialLoading).toBe(true);
  });

  it("shows blocking errors only when no stable data exists", () => {
    const { result, rerender } = renderHook(
      ({ data }: { data?: { id: string } }) =>
        useStableQueryData({
          data,
          resetKey: "error",
          error: new Error("boom"),
        }),
      { initialProps: { data: undefined } },
    );

    expect(result.current.showBlockingError).toBe(true);
    rerender({ data: { id: "ok" } });

    expect(result.current.showBlockingError).toBe(false);
  });

  it("ignores incompatible placeholder data", () => {
    const { result } = renderHook(() =>
      useStableQueryData({
        data: { session_id: "old" },
        resetKey: "new",
        isCompatible: (data) => data.session_id === "new",
        isPending: true,
      }),
    );

    expect(result.current.data).toBeNull();
    expect(result.current.initialLoading).toBe(true);
  });
});
