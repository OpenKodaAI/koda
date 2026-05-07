import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAsyncAction } from "@/hooks/use-async-action";
import { ToastProvider } from "@/hooks/use-toast";

describe("useAsyncAction", () => {
  it("tracks pending state and settles into success", async () => {
    let resolveAction: ((value: string) => void) | null = null;
    const { result } = renderHook(() => useAsyncAction(), {
      wrapper: ({ children }) => <ToastProvider>{children}</ToastProvider>,
    });

    let promise: Promise<string | undefined> | undefined;
    await act(async () => {
      promise = result.current.runAction(
        "save",
        () =>
          new Promise<string>((resolve) => {
            resolveAction = resolve;
          }),
        { successMessage: "ok" },
      );
    });

    await waitFor(() => {
      expect(result.current.isPending("save")).toBe(true);
      expect(result.current.getStatus("save")).toBe("pending");
    });

    await act(async () => {
      resolveAction?.("done");
      await promise;
    });

    expect(result.current.isPending("save")).toBe(false);
    expect(result.current.getStatus("save")).toBe("success");
  });

  it("dedupes the same key while an action is already pending", async () => {
    let resolveAction: (() => void) | null = null;
    const action = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveAction = resolve;
        }),
    );

    const { result } = renderHook(() => useAsyncAction(), {
      wrapper: ({ children }) => <ToastProvider>{children}</ToastProvider>,
    });

    await act(async () => {
      const current = result.current;
      void current.runAction("publish", action);
      void current.runAction("publish", action);
    });

    expect(action).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveAction?.();
    });
  });
});
