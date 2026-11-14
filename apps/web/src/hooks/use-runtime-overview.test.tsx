import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { STREAM_REJECTED_RETRY_MS } from "@/lib/sse";

vi.mock("@/components/providers/agent-catalog-provider", () => ({
  useAgentCatalog: () => ({ agents: [{ id: "agent-1" }] }),
}));

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
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ type, data: JSON.stringify(data) } as MessageEvent);
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

describe("useRuntimeOverview event stream", () => {
  beforeEach(() => {
    instances.length = 0;
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.stubGlobal("EventSource", MockEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          "agent-1": { agentId: "agent-1", availability: { runtime: "available" } },
        }),
      ),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  async function renderWithStream() {
    const rendered = renderHook(() => useRuntimeOverview(), { wrapper });
    await waitFor(() => expect(instances).toHaveLength(1));
    return { ...rendered, source: instances[0] };
  }

  it("reconnects after a transient stream failure", async () => {
    const { source } = await renderWithStream();

    act(() => {
      source.open();
      source.fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });

    expect(instances).toHaveLength(2);
  });

  it("retries a rejected stream request only after the slow retry delay", async () => {
    const { result, source } = await renderWithStream();

    act(() => {
      source.open();
    });
    expect(result.current.connected["agent-1"]).toBe(true);

    act(() => {
      source.dispatch("stream_error", { status: 400, error: "invalid after_seq" });
      // The relay then ends the response; a closed EventSource reports nothing.
      source.fail();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STREAM_REJECTED_RETRY_MS - 1_000);
    });

    expect(source.close).toHaveBeenCalled();
    expect(instances).toHaveLength(1);
    expect(result.current.connected["agent-1"]).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(instances).toHaveLength(2);
  });
});
