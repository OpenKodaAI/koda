import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/web-operator-session", () => ({
  getWebOperatorTokenFromCookie: vi.fn(),
}));

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: vi.fn(),
}));

vi.mock("@/lib/runtime-api", () => ({
  requireRuntimeBotConfig: vi.fn(),
  runtimeFetch: vi.fn(),
  runtimeFetchJson: vi.fn(),
  RuntimeRequestError: class RuntimeRequestError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("@/lib/runtime-relay", () => ({
  createRuntimeRelayDescriptor: vi.fn(),
  getRuntimeRelayPath: vi.fn((relayId: string) => `/api/runtime/relay/${relayId}`),
  toAbsoluteUpstreamWsUrl: vi.fn((_baseUrl: string, upstreamUrl: string) => upstreamUrl),
}));

describe("runtime task route security", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("blocks cross-site runtime mutations before proxying", async () => {
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");
    const { runtimeFetchJson } = await import("@/lib/runtime-api");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue("operator-token");
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(false);

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/runtime/bots/bot-1/tasks/7/attach/terminal", {
        method: "POST",
      }),
      {
        params: Promise.resolve({
          botId: "bot-1",
          taskId: "7",
          resource: ["attach", "terminal"],
        }),
      },
    );

    expect(response.status).toBe(403);
    expect(vi.mocked(runtimeFetchJson)).not.toHaveBeenCalled();
  });

  it("sanitizes terminal attach payloads and moves the token to relay headers", async () => {
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");
    const { requireRuntimeBotConfig, runtimeFetchJson } = await import("@/lib/runtime-api");
    const { createRuntimeRelayDescriptor } = await import("@/lib/runtime-relay");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue("operator-token");
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(true);
    vi.mocked(requireRuntimeBotConfig).mockResolvedValue({
      id: "bot-1",
      label: "Bot 1",
      color: "#000000",
      colorRgb: "0, 0, 0",
      healthUrl: "http://runtime.local/health",
      runtimeBaseUrl: "http://runtime.local",
      runtimeRequestToken: null,
      accessScopeToken: null,
    });
    vi.mocked(runtimeFetchJson).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        attach: {
          token: "attach-token",
          expires_at: "2026-04-05T12:00:00.000Z",
        },
        terminal: {
          id: 9,
        },
        ws_url: "ws://runtime.local/ws/runtime/tasks/7/terminals/9",
      },
    });
    vi.mocked(createRuntimeRelayDescriptor).mockResolvedValue({
      id: "relay-terminal-1",
      kind: "terminal",
      botId: "bot-1",
      taskId: 7,
      terminalId: 9,
      upstreamUrl: "ws://runtime.local/ws/runtime/tasks/7/terminals/9",
      upstreamHeaders: {
        "X-Koda-Attach-Token": "attach-token",
      },
      createdAt: "2026-04-05T11:55:00.000Z",
      expiresAt: "2026-04-05T12:00:00.000Z",
    });

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/runtime/bots/bot-1/tasks/7/attach/terminal", {
        method: "POST",
        headers: {
          Origin: "http://localhost",
        },
      }),
      {
        params: Promise.resolve({
          botId: "bot-1",
          taskId: "7",
          resource: ["attach", "terminal"],
        }),
      },
    );

    expect(response.status).toBe(200);

    const payload = await response.json();
    expect(payload.attach.token).toBeUndefined();
    expect(payload.ws_url).toBeUndefined();
    expect(payload.novnc_url).toBeUndefined();
    expect(payload.relay_path).toBe("/api/runtime/relay/relay-terminal-1");
    expect(createRuntimeRelayDescriptor).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "terminal",
        upstreamHeaders: {
          "X-Koda-Attach-Token": "attach-token",
        },
      }),
      expect.any(String),
    );
  });
});
