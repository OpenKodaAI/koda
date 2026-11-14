import { act, renderHook } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useSessionStream } from "@/hooks/use-session-stream";
import { STREAM_REJECTED_RETRY_MS } from "@/lib/sse";

type MessageListener = (event: MessageEvent) => void;
type ErrorListener = () => void;

interface FakeEventSource {
  url: string;
  readyState: number;
  close: ReturnType<typeof vi.fn>;
  onopen: (() => void) | null;
  onmessage: MessageListener | null;
  onerror: ErrorListener | null;
  addEventListener: ReturnType<typeof vi.fn>;
  emit: (data: unknown) => void;
  dispatch: (type: string, data: unknown) => void;
  triggerOpen: () => void;
  triggerError: () => void;
}

const instances: FakeEventSource[] = [];

class MockEventSource implements FakeEventSource {
  public readyState = 0;
  public onopen: (() => void) | null = null;
  public onmessage: MessageListener | null = null;
  public onerror: ErrorListener | null = null;
  public close = vi.fn(() => {
    this.readyState = 2;
  });
  private listeners = new Map<string, MessageListener[]>();
  public addEventListener = vi.fn((type: string, listener: MessageListener) => {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  });

  constructor(public url: string) {
    instances.push(this);
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  dispatch(type: string, data: unknown) {
    if (this.readyState === 2) return;
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ type, data: JSON.stringify(data) } as MessageEvent);
    }
  }

  triggerOpen() {
    this.readyState = 1;
    this.onopen?.();
  }

  triggerError() {
    this.readyState = 2;
    this.onerror?.();
  }
}

describe("useSessionStream", () => {
  beforeEach(() => {
    instances.length = 0;
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("connects to the runtime session stream and dispatches events", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
        onEvent,
      }),
    );

    expect(instances).toHaveLength(1);
    const source = instances[0];
    expect(source.url).toBe(
      "/api/runtime/agents/bot-1/sessions/sess-1/stream",
    );

    act(() => {
      source.triggerOpen();
    });
    expect(result.current.connected).toBe(true);

    const event = {
      seq: 12,
      type: "task_complete",
      task_id: 7,
      payload: { status: "ok" },
    };
    act(() => {
      source.emit(event);
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ seq: 12, type: "task_complete" }),
    );
    expect(result.current.lastEvent?.seq).toBe(12);
  });

  it("reconnects after error with after_seq continuation", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
      }),
    );

    expect(instances).toHaveLength(1);
    const first = instances[0];
    act(() => {
      first.triggerOpen();
      first.emit({ seq: 5, type: "task_started", task_id: 1, payload: {} });
      first.triggerError();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });

    expect(instances.length).toBeGreaterThanOrEqual(2);
    const second = instances[instances.length - 1];
    expect(second.url).toContain("after_seq=5");
  });

  it("resumes from global event ids above 1000", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
      }),
    );

    const first = instances[0];
    act(() => {
      first.triggerOpen();
      first.emit({ seq: 1_500, type: "task_started", task_id: 1, payload: {} });
      first.triggerError();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });

    expect(instances[instances.length - 1].url).toContain("after_seq=1500");
  });

  it("grows the backoff while connections fail without opening", async () => {
    // The session relay answers transient failures with a non-200 status, so
    // EventSource reports `error` without `open` and the backoff keeps growing.
    vi.useFakeTimers({ shouldAdvanceTime: false });
    renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
      }),
    );

    act(() => {
      instances[0].triggerError();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });
    expect(instances).toHaveLength(2);

    act(() => {
      instances[1].triggerError();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_999);
    });
    expect(instances).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(instances).toHaveLength(3);
  });

  it("keeps the reason and retries only after the slow retry delay on stream_error", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    const { result } = renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
      }),
    );

    const first = instances[0];
    act(() => {
      first.triggerOpen();
      first.dispatch("stream_error", { status: 400, error: "invalid after_seq" });
      // The relay then ends the response; a closed EventSource reports nothing.
      if (first.readyState !== 2) first.triggerError();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(STREAM_REJECTED_RETRY_MS - 1);
    });

    expect(first.close).toHaveBeenCalled();
    expect(instances).toHaveLength(1);
    expect(result.current.connected).toBe(false);
    expect(result.current.error).toBe("invalid after_seq");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(instances).toHaveLength(2);
  });

  it("reconnects immediately on demand after a stream_error", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    const { result } = renderHook(() =>
      useSessionStream({
        agentId: "bot-1",
        sessionId: "sess-1",
      }),
    );

    act(() => {
      instances[0].triggerOpen();
      instances[0].dispatch("stream_error", { status: 404, error: "task not found" });
    });
    act(() => {
      result.current.reconnect();
    });
    expect(instances).toHaveLength(2);

    // The manual reconnect replaces the pending slow retry.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STREAM_REJECTED_RETRY_MS);
    });
    expect(instances).toHaveLength(2);
  });

  it("does not connect when disabled or ids missing", () => {
    const { rerender } = renderHook(
      ({ enabled, sessionId }: { enabled: boolean; sessionId: string | null }) =>
        useSessionStream({
          agentId: "bot-1",
          sessionId,
          enabled,
        }),
      { initialProps: { enabled: false, sessionId: "sess-1" } },
    );

    expect(instances).toHaveLength(0);

    rerender({ enabled: true, sessionId: null });
    expect(instances).toHaveLength(0);
  });
});
