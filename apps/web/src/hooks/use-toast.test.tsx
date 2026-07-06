import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "@/hooks/use-toast";

function wrap(children: React.ReactNode) {
  return <ToastProvider>{children}</ToastProvider>;
}

describe("useToast (persistent + progress + updateToast)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("auto-dismisses non-persistent toasts after durationMs", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    act(() => {
      result.current.showToast("hello", "info", { durationMs: 1000 });
    });
    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(result.current.toasts).toHaveLength(0);
  });

  it("does NOT auto-dismiss persistent toasts even after a long time", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    act(() => {
      result.current.showToast("Baixando...", "loading", {
        persistent: true,
        progress: { downloaded: 0, total: 100 },
      });
    });

    act(() => {
      vi.advanceTimersByTime(60_000); // a full minute
    });
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].persistent).toBe(true);
  });

  it("updateToast patches partial fields without spawning a new toast", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    let id = "";
    act(() => {
      id = result.current.showToast("Baixando...", "loading", {
        persistent: true,
        progress: { downloaded: 0, total: 1000 },
      });
    });

    act(() => {
      result.current.updateToast(id, {
        progress: { downloaded: 250, total: 1000 },
      });
    });
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].progress).toEqual({ downloaded: 250, total: 1000 });
    // Persistent flag preserved.
    expect(result.current.toasts[0].persistent).toBe(true);
  });

  it("converting persistent → non-persistent schedules auto-dismiss", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    let id = "";
    act(() => {
      id = result.current.showToast("Baixando...", "loading", { persistent: true });
    });

    act(() => {
      result.current.updateToast(id, {
        type: "success",
        message: "Pronto!",
        persistent: false,
        durationMs: 2000,
        progress: undefined,
      });
    });

    // Still present immediately after the morph.
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].type).toBe("success");

    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(result.current.toasts).toHaveLength(0);
  });

  it("showToast with a stable id replaces the existing toast in place", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    act(() => {
      result.current.showToast("v1", "loading", { id: "download:abc", persistent: true });
    });
    act(() => {
      result.current.showToast("v2", "loading", { id: "download:abc", persistent: true });
    });

    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].message).toBe("v2");
  });

  it("updateToast on a non-existent id is a no-op", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ({ children }) => wrap(children) });

    act(() => {
      result.current.updateToast("does-not-exist", { message: "x" });
    });
    expect(result.current.toasts).toHaveLength(0);
  });
});
