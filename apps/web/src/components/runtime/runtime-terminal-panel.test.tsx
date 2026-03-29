import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";

const mockTerminal = {
  loadAddon: vi.fn(),
  open: vi.fn(),
  focus: vi.fn(),
  writeln: vi.fn(),
  onData: vi.fn(() => ({ dispose: vi.fn() })),
  reset: vi.fn(),
  write: vi.fn(),
  dispose: vi.fn(),
  unicode: { activeVersion: "6" },
};

const mockFitAddon = {
  fit: vi.fn(),
};

class MockResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

class MockWebSocket {
  static OPEN = 1;

  readyState = MockWebSocket.OPEN;
  addEventListener = vi.fn();
  close = vi.fn();
  send = vi.fn();

  constructor(public readonly url: string) {}
}

vi.mock("@xterm/xterm", () => ({
  Terminal: class Terminal {
    constructor() {
      return mockTerminal;
    }
  },
}));

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class FitAddon {
    constructor() {
      return mockFitAddon;
    }
  },
}));

vi.mock("@xterm/addon-webgl", () => ({
  WebglAddon: class {
    onContextLoss = vi.fn();
    dispose = vi.fn();
  },
}));

vi.mock("@xterm/addon-web-links", () => ({
  WebLinksAddon: class {},
}));

vi.mock("@xterm/addon-search", () => ({
  SearchAddon: class {
    findNext = vi.fn();
    findPrevious = vi.fn();
  },
}));

vi.mock("@xterm/addon-unicode11", () => ({
  Unicode11Addon: class {},
}));

describe("RuntimeTerminalPanel", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("avoids creating a duplicate auto-attach when the first attach returns a terminal id", async () => {
    const mutate = vi.fn().mockResolvedValue({
      attach: {
        task_id: 7,
        can_write: false,
        expires_at: "2026-03-19T12:00:00.000Z",
      },
      terminal: {
        id: 42,
        task_id: 7,
        label: "Operador",
      },
      relay_path: "/api/runtime/relay/test-terminal",
    });
    const fetchResource = vi.fn().mockResolvedValue({ items: [] });

    const { RuntimeTerminalPanel } = await import("@/components/runtime/runtime-terminal-panel");

    render(
      <I18nProvider initialLanguage="pt-BR">
        <RuntimeTerminalPanel
          taskId={7}
          terminals={[]}
          mutate={mutate}
          fetchResource={fetchResource}
        />
      </I18nProvider>
    );

    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    expect(mutate.mock.calls[0]?.[0]).toBe("attach/terminal");
    expect(
      mutate.mock.calls[0]?.[1]?.searchParams instanceof URLSearchParams
    ).toBe(true);
    expect(mutate.mock.calls[0]?.[1]?.searchParams.get("terminal_id")).toBeNull();

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 30));
    });

    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it("prefers the newest interactive terminal for auto-attach", async () => {
    const mutate = vi.fn().mockResolvedValue({
      attach: {
        task_id: 7,
        can_write: false,
        expires_at: "2026-03-19T12:00:00.000Z",
      },
      terminal: {
        id: 11,
        task_id: 7,
        label: "operator shell",
      },
      relay_path: "/api/runtime/relay/test-terminal",
    });
    const fetchResource = vi.fn().mockResolvedValue({ items: [] });

    const { RuntimeTerminalPanel } = await import("@/components/runtime/runtime-terminal-panel");

    render(
      <I18nProvider initialLanguage="pt-BR">
        <RuntimeTerminalPanel
          taskId={7}
          terminals={[
            {
              id: 5,
              task_id: 7,
              label: "claude stream",
              interactive: false,
            },
            {
              id: 9,
              task_id: 7,
              label: "operator shell",
              interactive: true,
            },
            {
              id: 11,
              task_id: 7,
              label: "operator shell",
              interactive: true,
            },
          ]}
          mutate={mutate}
          fetchResource={fetchResource}
        />
      </I18nProvider>
    );

    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    expect(mutate.mock.calls[0]?.[1]?.searchParams.get("terminal_id")).toBe("11");
  });
});
