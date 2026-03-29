import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("control-plane security gates", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("fails closed when the operator session cookie is missing", async () => {
    vi.doMock("@/lib/web-operator-session", () => ({
      getWebOperatorTokenFromCookie: vi.fn(async () => null),
    }));

    const { controlPlaneFetch } = await import("@/lib/control-plane");

    await expect(controlPlaneFetch("/api/control-plane/agents")).rejects.toMatchObject({
      status: 401,
      message: "Operator session is required",
    });
  });

  it("forwards the sealed operator token as bearer auth", async () => {
    vi.doMock("@/lib/web-operator-session", () => ({
      getWebOperatorTokenFromCookie: vi.fn(async () => "operator-token"),
    }));

    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { controlPlaneFetch } = await import("@/lib/control-plane");

    await controlPlaneFetch("/api/control-plane/agents");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const firstCall = fetchMock.mock.calls[0] as
      | [RequestInfo | URL, RequestInit | undefined]
      | undefined;
    const init = firstCall?.[1];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer operator-token");
  });
});
