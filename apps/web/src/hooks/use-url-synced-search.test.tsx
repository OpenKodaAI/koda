import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUrlSyncedSearch } from "@/hooks/use-url-synced-search";

function setLocation(path: string) {
  window.history.replaceState(null, "", path);
}

describe("useUrlSyncedSearch", () => {
  beforeEach(() => {
    setLocation("/sessions");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hydrates from the current URL", () => {
    setLocation("/sessions?search=Beta");

    const { result } = renderHook(() => useUrlSyncedSearch({ debounceMs: 50 }));

    expect(result.current.value).toBe("Beta");
    expect(result.current.debouncedValue).toBe("Beta");
  });

  it("debounces writes through history.replaceState", async () => {
    const replaceState = vi.spyOn(window.history, "replaceState");
    const { result } = renderHook(() => useUrlSyncedSearch({ debounceMs: 5 }));

    act(() => {
      result.current.setValue("Beta");
    });

    expect(result.current.isSearching).toBe(true);
    expect(window.location.search).toBe("");

    await waitFor(() => {
      expect(window.location.search).toBe("?search=Beta");
    });

    expect(replaceState).toHaveBeenCalledWith(null, "", "/sessions?search=Beta");
  });

  it("removes an empty search param without touching other params", async () => {
    setLocation("/sessions?agent=ATLAS&search=Beta");
    const { result } = renderHook(() => useUrlSyncedSearch({ debounceMs: 5 }));

    act(() => {
      result.current.clear();
    });

    await waitFor(() => {
      expect(window.location.search).toBe("?agent=ATLAS");
    });
  });

  it("reacts to browser popstate", () => {
    setLocation("/sessions?search=Alpha");
    const { result } = renderHook(() => useUrlSyncedSearch({ debounceMs: 50 }));

    act(() => {
      window.history.pushState(null, "", "/sessions?search=Beta");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current.value).toBe("Beta");
  });
});
