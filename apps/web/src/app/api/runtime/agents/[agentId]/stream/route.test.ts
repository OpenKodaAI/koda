import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/runtime-api", () => ({
  runtimeFetch: vi.fn(),
  RuntimeRequestError: class RuntimeRequestError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

const params = Promise.resolve({ agentId: "agent-1" });

function request(query = "") {
  return new Request(`http://localhost/api/runtime/agents/agent-1/stream${query}`);
}

describe("runtime agent stream relay", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("forwards the resume cursor upstream", async () => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const { GET } = await import("./route");
    const response = await GET(request("?task_id=7&after_seq=1500"), { params });

    expect(response.status).toBe(200);
    const searchParams = vi.mocked(runtimeFetch).mock.calls[0]?.[3];
    expect(searchParams?.get("after_seq")).toBe("1500");
    expect(searchParams?.get("task_id")).toBe("7");
  });

  it.each([
    [400, "invalid after_seq"],
    [404, '{"error":"task not found"}'],
    [422, "unprocessable"],
  ])(
    "turns a %i the runtime returned into a stream_error event",
    async (status, upstreamBody) => {
      const { runtimeFetch } = await import("@/lib/runtime-api");
      vi.mocked(runtimeFetch).mockResolvedValue(new Response(upstreamBody, { status }));

      const { GET } = await import("./route");
      const response = await GET(request("?after_seq=abc"), { params });

      expect(response.status).toBe(200);
      expect(response.headers.get("Content-Type")).toContain("text/event-stream");
      const body = await response.text();
      expect(body).toContain("retry: 60000\n");
      expect(body).toContain("event: stream_error\n");
      // Only the status: no client reads the upstream message.
      expect(body).toContain(`data: ${JSON.stringify({ status })}\n\n`);
    },
  );

  // A missing or stale runtime token (the control plane did not hand one out)
  // and server-side failures clear up on their own; EventSource must keep
  // reconnecting with its normal backoff.
  it.each([401, 403, 408, 429, 500, 503])(
    "keeps the upstream status for a transient %i",
    async (status) => {
      const { runtimeFetch } = await import("@/lib/runtime-api");
      vi.mocked(runtimeFetch).mockResolvedValue(new Response("busy", { status }));

      const { GET } = await import("./route");
      const response = await GET(request(), { params });

      expect(response.status).toBe(status);
      expect(response.headers.get("Content-Type")).not.toContain("text/event-stream");
      await expect(response.json()).resolves.toEqual({ error: "busy" });
    },
  );

  it("keeps failures raised before the runtime answered retryable", async () => {
    // requireRuntimeAgentConfig reports any control-plane failure, including an
    // outage during a deploy, as "Agent not found" (404).
    const { runtimeFetch, RuntimeRequestError } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockRejectedValue(new RuntimeRequestError("Agent not found", 404));

    const { GET } = await import("./route");
    const response = await GET(request(), { params });

    expect(response.status).toBe(404);
    expect(response.headers.get("Content-Type")).not.toContain("text/event-stream");
    await expect(response.json()).resolves.toEqual({ error: "Agent not found" });
  });

  it("keeps an unreachable runtime retryable", async () => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockRejectedValue(new TypeError("fetch failed"));

    const { GET } = await import("./route");
    const response = await GET(request(), { params });

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toEqual({ error: "fetch failed" });
  });
});
