import { act, renderHook } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useSessionStream } from "@/hooks/use-session-stream";

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
  public addEventListener = vi.fn();

  constructor(public url: string) {
    instances.push(this);
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
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
