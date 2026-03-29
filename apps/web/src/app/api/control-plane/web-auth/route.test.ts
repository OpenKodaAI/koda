import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("control-plane web auth route", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.CONTROL_PLANE_BASE_URL = "http://control.local";
  });

  afterEach(() => {
    delete process.env.CONTROL_PLANE_BASE_URL;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("seals a verified operator token into an http-only cookie", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe("http://control.local/api/control-plane/onboarding/status");
      expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer operator-token");
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { POST, DELETE } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/control-plane/web-auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ token: "operator-token" }),
      }) as never,
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("koda_operator_session=");
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const cleared = await DELETE();
    expect(cleared.headers.get("set-cookie")).toContain("koda_operator_session=");
    expect(cleared.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("rejects invalid control-plane tokens", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 401 })));

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/control-plane/web-auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ token: "invalid-token" }),
      }) as never,
    );

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
