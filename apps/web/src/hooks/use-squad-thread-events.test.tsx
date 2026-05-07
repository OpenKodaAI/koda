import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useSquadThreadEvents,
  type SquadThreadEvent,
} from "@/hooks/use-squad-thread-events";

type Listener = (event: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  readyState = 0;
  listeners: Record<string, Listener[]> = {};
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    (this.listeners[type] ??= []).push(listener);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    for (const listener of this.listeners[type] ?? []) {
      listener(event);
    }
  }

  static reset() {
    MockEventSource.instances = [];
  }
}

beforeEach(() => {
  MockEventSource.reset();
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useSquadThreadEvents", () => {
  it("opens an EventSource and dispatches matching events", () => {
    const onEvent = vi.fn();
    const { result, unmount } = renderHook(() =>
      useSquadThreadEvents({ threadId: "abc-thread", onEvent }),
    );

    expect(result.current).toBe("connecting");
    expect(MockEventSource.instances).toHaveLength(1);
    const source = MockEventSource.instances[0];
    expect(source.url).toContain("/api/control-plane/dashboard/squads/threads/abc-thread/events");

    act(() => {
      source.emit("open", undefined);
    });
    expect(result.current).toBe("open");

    const payload: SquadThreadEvent = {
      thread_id: "abc-thread",
      event_type: "message_added",
      data: { message_id: 5 },
    };
    act(() => {
      source.emit("message_added", payload);
    });
    expect(onEvent).toHaveBeenCalledWith(payload);

    unmount();
    expect(source.closed).toBe(true);
  });

  it("ignores events for other threads", () => {
    const onEvent = vi.fn();
    renderHook(() => useSquadThreadEvents({ threadId: "abc-thread", onEvent }));
    const source = MockEventSource.instances[0];
    act(() => {
      source.emit("message_added", { thread_id: "other-thread", event_type: "message_added" });
    });
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("transitions to error status when the stream errors", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() =>
      useSquadThreadEvents({ threadId: "abc-thread", onEvent }),
    );
    const source = MockEventSource.instances[0];
    act(() => {
      source.emit("error", undefined);
    });
    expect(result.current).toBe("error");
  });

  it("does not open a stream when disabled", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() =>
      useSquadThreadEvents({ threadId: "abc-thread", onEvent, enabled: false }),
    );
    expect(result.current).toBe("idle");
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("ignores malformed event payloads", () => {
    const onEvent = vi.fn();
    renderHook(() => useSquadThreadEvents({ threadId: "abc-thread", onEvent }));
    const source = MockEventSource.instances[0];
    act(() => {
      // Synthesize a raw broken payload.
      const event = { data: "not-json" } as MessageEvent;
      for (const listener of source.listeners["message_added"] ?? []) {
        listener(event);
      }
    });
    expect(onEvent).not.toHaveBeenCalled();
  });
});
