import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next/cache", () => ({
  revalidatePath: vi.fn(),
  revalidateTag: vi.fn(),
}));

vi.mock("@/lib/control-plane", () => ({
  controlPlaneFetch: vi.fn(),
  sanitizeControlPlanePayload: vi.fn((_pathname: string, payload: unknown) => payload),
}));

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: vi.fn(),
}));

vi.mock("@/lib/web-operator-session", () => ({
  getWebOperatorTokenFromCookie: vi.fn(),
  setOwnerExistsHintCookie: vi.fn(),
}));

function request(url: string, method = "GET") {
  return new NextRequest(url, {
    method,
    headers: {
      Origin: "http://localhost",
    },
  });
}

describe("control plane proxy route", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("returns an empty successful dashboard summary when the upstream is unavailable", async () => {
    const { controlPlaneFetch } = await import("@/lib/control-plane");
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue("operator-token");
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(true);
    vi.mocked(controlPlaneFetch).mockRejectedValue(Object.assign(new Error("down"), { status: 503 }));

    const { GET } = await import("./route");
    const response = await GET(
      request("http://localhost/api/control-plane/dashboard/agents/summary?recentTaskLimit=0"),
      { params: Promise.resolve({ path: ["dashboard", "agents", "summary"] }) },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("x-koda-upstream-unavailable")).toBe("1");
    expect(await response.json()).toEqual([]);
  });

  it("preserves pagination shape for unavailable dashboard execution lists", async () => {
    const { controlPlaneFetch } = await import("@/lib/control-plane");
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue("operator-token");
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(true);
    vi.mocked(controlPlaneFetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "offline" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { GET } = await import("./route");
    const response = await GET(
      request("http://localhost/api/control-plane/dashboard/executions?paged=1&limit=25&offset=50"),
      { params: Promise.resolve({ path: ["dashboard", "executions"] }) },
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      items: [],
      page: {
        limit: 25,
        offset: 50,
        returned: 0,
        next_offset: null,
        has_more: false,
      },
      unavailable: true,
    });
  });

  it("keeps mutations as hard failures when the upstream is unavailable", async () => {
    const { controlPlaneFetch } = await import("@/lib/control-plane");
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue("operator-token");
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(true);
    vi.mocked(controlPlaneFetch).mockRejectedValue(Object.assign(new Error("down"), { status: 503 }));

    const { DELETE } = await import("./route");
    const response = await DELETE(
      request("http://localhost/api/control-plane/dashboard/squads/threads/thread-1", "DELETE"),
      { params: Promise.resolve({ path: ["dashboard", "squads", "threads", "thread-1"] }) },
    );

    expect(response.status).toBe(503);
    expect(response.headers.get("x-koda-upstream-unavailable")).toBeNull();
  });

  it("softens public onboarding readiness probes while preserving the schema", async () => {
    const { controlPlaneFetch } = await import("@/lib/control-plane");
    const { getWebOperatorTokenFromCookie } = await import("@/lib/web-operator-session");
    const { isTrustedDashboardRequest } = await import("@/lib/request-origin");

    vi.mocked(getWebOperatorTokenFromCookie).mockResolvedValue(null);
    vi.mocked(isTrustedDashboardRequest).mockReturnValue(true);
    vi.mocked(controlPlaneFetch).mockRejectedValue(Object.assign(new Error("down"), { status: 503 }));

    const { GET } = await import("./route");
    const response = await GET(
      request("http://localhost/api/control-plane/onboarding/readiness"),
      { params: Promise.resolve({ path: ["onboarding", "readiness"] }) },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("x-koda-upstream-unavailable")).toBe("1");
    expect(await response.json()).toMatchObject({
      schema_version: "onboarding_readiness.v1",
      status: "pending",
      checks: [],
      actions: [],
    });
  });
});
