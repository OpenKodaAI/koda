import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { useRuntimeTask } from "@/hooks/use-runtime-task";
import { STREAM_REJECTED_RETRY_MS } from "@/lib/sse";

type Listener = (event: MessageEvent) => void;

const instances: MockEventSource[] = [];

class MockEventSource {
  public readyState = 0;
  public onopen: (() => void) | null = null;
  public onmessage: Listener | null = null;
  public onerror: (() => void) | null = null;
  private listeners = new Map<string, Listener[]>();
  public close = vi.fn(() => {
    this.readyState = 2;
  });

  constructor(public url: string) {
    instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  dispatch(type: string, data: unknown) {
    if (this.readyState === 2) return;
    const event = { type, data: JSON.stringify(data) } as MessageEvent;
    if (type === "message") this.onmessage?.(event);
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }

  fail() {
    if (this.readyState === 2) return;
    this.readyState = 2;
    this.onerror?.();
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">{children}</I18nProvider>
    </QueryClientProvider>
  );
}

describe("useRuntimeTask event stream", () => {
  beforeEach(() => {
    instances.length = 0;
    vi.useFakeTimers({ shouldAdvanceTime: false });
    vi.stubGlobal("EventSource", MockEventSource);
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reconnects after a transient stream failure", async () => {
    renderHook(() => useRuntimeTask("agent-1", 7), { wrapper });
    expect(instances).toHaveLength(1);

    act(() => {
      instances[0].open();
      instances[0].fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });

    expect(instances).toHaveLength(2);
  });

  it("retries a rejected stream request only after the slow retry delay", async () => {
    const { result } = renderHook(() => useRuntimeTask("agent-1", 7), { wrapper });
    const source = instances[0];

    act(() => {
      source.open();
      source.dispatch("message", { seq: 1_500, type: "task_progress", task_id: 7 });
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      source.dispatch("stream_error", { status: 400 });
      // The relay then ends the response; a closed EventSource reports nothing.
      source.fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STREAM_REJECTED_RETRY_MS - 1);
    });

    expect(source.close).toHaveBeenCalled();
    expect(instances).toHaveLength(1);
    expect(result.current.connected).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(instances).toHaveLength(2);
    expect(instances[1].url).toContain("after_seq=1500");
  });

  it("closes the latest connection on unmount after a reconnect", async () => {
    const { unmount } = renderHook(() => useRuntimeTask("agent-1", 7), { wrapper });

    act(() => {
      instances[0].open();
      instances[0].fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(instances).toHaveLength(2);

    unmount();

    expect(instances[1].close).toHaveBeenCalled();
  });
});
