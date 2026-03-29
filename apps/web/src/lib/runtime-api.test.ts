import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/web-operator-session", () => ({
  getWebOperatorTokenFromCookie: vi.fn(async () => "operator-token"),
}));

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("runtime-api", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds overviews from canonical runtime readiness instead of raw /health", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/api/control-plane/agents/ATLAS/runtime-access")) {
        return jsonResponse({
          bot_id: "ATLAS",
          health_url: "http://runtime.local/health",
          runtime_base_url: "http://runtime.local",
          runtime_token: "runtime-token",
          access_scope_token: "scope-token",
          runtime_token_present: true,
        });
      }

      if (url.includes("/api/control-plane/agents/ATLAS")) {
        return jsonResponse({
          id: "ATLAS",
          display_name: "ATLAS",
          status: "active",
          appearance: { label: "ATLAS", color: "#ffffff", color_rgb: "255,255,255" },
          storage_namespace: "masp",
          runtime_endpoint: {
            health_url: "http://runtime.local/health",
            runtime_base_url: "http://runtime.local",
          },
          metadata: {},
          organization: {},
        });
      }

      if (url === "http://runtime.local/api/runtime/readiness") {
        return jsonResponse({
          ready: true,
          startup: { phase: "ready" },
          background_loops: { critical_ready: true, degraded_loops: [] },
          knowledge_v2: { ready: true, primary_backend: { ready: true } },
        });
      }

      if (url === "http://runtime.local/api/runtime/queues") {
        return jsonResponse({
          items: [{ task_id: 7, status: "running", query_text: "review PR" }],
        });
      }

      if (url === "http://runtime.local/api/runtime/environments") {
        return jsonResponse({
          items: [
            {
              id: 11,
              task_id: 7,
              status: "active",
              current_phase: "running",
              updated_at: "2026-03-27T12:00:00Z",
            },
          ],
        });
      }

      if (url === "http://runtime.local/health") {
        throw new Error("raw health should not be called");
      }

      throw new Error(`unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    const { getRuntimeOverview } = await import("@/lib/runtime-api");
    const overview = await getRuntimeOverview("ATLAS");

    expect(overview.readiness?.ready).toBe(true);
    expect(overview.activeTaskIds).toEqual([7]);
    expect(fetchMock).not.toHaveBeenCalledWith(
      "http://runtime.local/health",
      expect.anything(),
    );
  });

  it("injects scoped runtime access only on sensitive runtime reads", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("/api/control-plane/agents/ATLAS/runtime-access")) {
        return jsonResponse({
          bot_id: "ATLAS",
          health_url: "http://runtime.local/health",
          runtime_base_url: "http://runtime.local",
          runtime_token: "runtime-token",
          access_scope_token: "scope-token",
          runtime_token_present: true,
        });
      }

      if (url.includes("/api/control-plane/agents/ATLAS")) {
        return jsonResponse({
          id: "ATLAS",
          display_name: "ATLAS",
          status: "active",
          appearance: { label: "ATLAS", color: "#ffffff", color_rgb: "255,255,255" },
          storage_namespace: "masp",
          runtime_endpoint: {
            health_url: "http://runtime.local/health",
            runtime_base_url: "http://runtime.local",
          },
          metadata: {},
          organization: {},
        });
      }

      if (url === "http://runtime.local/api/runtime/tasks/7?include_sensitive=true") {
        const headers = new Headers(init?.headers);
        expect(headers.get("X-Runtime-Token")).toBe("runtime-token");
        expect(headers.get("X-Runtime-Access-Scope")).toBe("scope-token");
        return jsonResponse({ task: { id: 7, status: "running" } });
      }

      throw new Error(`unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    const { runtimeFetchJson } = await import("@/lib/runtime-api");
    const result = await runtimeFetchJson(
      "ATLAS",
      "/api/runtime/tasks/7",
      {},
      new URLSearchParams({ include_sensitive: "true" }),
    );

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
  });
});
