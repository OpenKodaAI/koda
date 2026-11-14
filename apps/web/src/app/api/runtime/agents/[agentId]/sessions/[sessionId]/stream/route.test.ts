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

const params = Promise.resolve({ agentId: "agent-1", sessionId: "sess-1" });

function request(query = "") {
  return new Request(`http://localhost/api/runtime/agents/agent-1/sessions/sess-1/stream${query}`);
}

describe("runtime session stream relay", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("forwards the resume cursor and session id upstream", async () => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const { GET } = await import("./route");
    const response = await GET(request("?after_seq=1500"), { params });

    expect(response.status).toBe(200);
    const searchParams = vi.mocked(runtimeFetch).mock.calls[0]?.[3];
    expect(searchParams?.get("after_seq")).toBe("1500");
    expect(searchParams?.get("session_id")).toBe("sess-1");
  });

  it("turns a request the runtime rejected into a stream_error event", async () => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockResolvedValue(
      new Response("invalid after_seq", { status: 400 }),
    );

    const { GET } = await import("./route");
    const response = await GET(request("?after_seq=-1"), { params });

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");
    const body = await response.text();
    expect(body).toContain("event: stream_error\n");
    expect(body).toContain('data: {"status":400}\n\n');
  });

  // An empty 200 stream here used to fire EventSource `open`, which reset the
  // hook's backoff, so a runtime outage was retried every 1.5s forever. A
  // non-200 status fails the EventSource without opening it.
  it.each([403, 500, 503])("answers a transient upstream %i with a non-200 status", async (status) => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockResolvedValue(new Response("busy", { status }));

    const { GET } = await import("./route");
    const response = await GET(request(), { params });

    expect(response.status).toBe(status);
    expect(response.headers.get("Content-Type")).not.toContain("text/event-stream");
    await expect(response.json()).resolves.toEqual({ error: "busy" });
  });

  it("keeps failures raised before the runtime answered retryable", async () => {
    const { runtimeFetch, RuntimeRequestError } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockRejectedValue(new RuntimeRequestError("Agent not found", 404));

    const { GET } = await import("./route");
    const response = await GET(request(), { params });

    expect(response.status).toBe(404);
    expect(response.headers.get("Content-Type")).not.toContain("text/event-stream");
    expect(await response.text()).not.toContain("stream_error");
  });

  it("answers an upstream 200 without a body with a non-200 status", async () => {
    const { runtimeFetch } = await import("@/lib/runtime-api");
    vi.mocked(runtimeFetch).mockResolvedValue(new Response(null, { status: 200 }));

    const { GET } = await import("./route");
    const response = await GET(request(), { params });

    expect(response.status).toBe(502);
  });
});
