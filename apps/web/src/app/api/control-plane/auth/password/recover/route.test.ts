import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const upstreamFetch = vi.fn();

vi.mock("@/lib/api-utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-utils")>();
  return { ...actual, upstreamFetch };
});

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: () => true,
}));

const VALID_RECOVER_BODY = JSON.stringify({
  identifier: "owner@example.com",
  recovery_code: "ABCD-EFGH-JKLM",
  new_password: "a-strong-password-123",
});
const PLAIN_HTTP_LAN = { Origin: "http://192.168.1.10:3000", "X-Forwarded-Proto": "http" };
const PLAIN_HTTP_RECOVER_URL = "http://192.168.1.10:3000/api/control-plane/auth/password/recover";

function recoverRequest(
  headers: Record<string, string> = {},
  url = "http://127.0.0.1:3000/api/control-plane/auth/password/recover",
  body = VALID_RECOVER_BODY,
): NextRequest {
  return new NextRequest(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
  });
}

describe("POST /api/control-plane/auth/password/recover", () => {
  beforeEach(() => {
    upstreamFetch.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("refuses plain HTTP from a LAN address before the recovery code is sent upstream (J-14)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    upstreamFetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const { POST } = await import("./route");

    const response = await POST(recoverRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_RECOVER_URL));
    const body = (await response.json()) as { error?: { code?: string; message?: string } };

    // The code and the new password would cross the network in clear text,
    // every session would be revoked, and the operator would land on a /login
    // that cannot sign in from this browser.
    expect(response.status).toBe(403);
    expect(body.error?.code).toBe("INSECURE_TRANSPORT");
    expect(body.error?.message).toContain("http://192.168.1.10:3000");
    expect(upstreamFetch).not.toHaveBeenCalled();
    expect(response.headers.get("cache-control")).toBe("no-store");

    // The same recovery through a proxy that terminated HTTPS goes through.
    const viaHttps = await POST(
      recoverRequest(
        { Origin: "https://koda.example.com", Host: "koda.example.com", "X-Forwarded-Proto": "https" },
        "http://koda.example.com/api/control-plane/auth/password/recover",
      ),
    );

    expect(viaHttps.status).toBe(200);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
  });

  it("refuses plain HTTP from the transport alone, before the body is read", async () => {
    // The refusal is the one specific auth error the screens show, which is
    // safe only because no credential decides it (apps/web/CLAUDE.md).
    vi.stubEnv("NODE_ENV", "production");
    const { POST } = await import("./route");

    const refusals: string[] = [];
    for (const body of [VALID_RECOVER_BODY, "{}", "identifier=owner%40example.com&recovery_code=ABCD"]) {
      const request = recoverRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_RECOVER_URL, body);
      const response = await POST(request);

      expect(response.status, body).toBe(403);
      expect(response.headers.get("cache-control"), body).toBe("no-store");
      expect(request.bodyUsed, body).toBe(false);
      refusals.push(await response.text());
    }

    expect(new Set(refusals)).toEqual(new Set([refusals[0]]));
    expect((JSON.parse(refusals[0]) as { error: { code: string } }).error.code).toBe("INSECURE_TRANSPORT");
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("forwards the browser address so the control plane rate limits each client separately", async () => {
    upstreamFetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const { POST } = await import("./route");

    const response = await POST(recoverRequest({ "X-Forwarded-For": "10.9.9.9, 198.51.100.7" }));

    expect(response.status).toBe(200);
    const init = upstreamFetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(new Headers(init?.headers).get("X-Forwarded-For")).toBe("198.51.100.7");
  });
});
