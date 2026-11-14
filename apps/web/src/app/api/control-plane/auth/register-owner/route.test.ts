import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  OWNER_EXISTS_HINT_COOKIE,
  PENDING_RECOVERY_COOKIE,
  WEB_OPERATOR_SESSION_COOKIE,
} from "@/lib/web-operator-session-constants";

const upstreamFetch = vi.fn();

vi.mock("@/lib/api-utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-utils")>();
  return { ...actual, upstreamFetch };
});

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: () => true,
}));

const VALID_REGISTER_BODY = JSON.stringify({
  email: "owner@example.com",
  password: "a-strong-password-123",
  bootstrap_code: "CODE",
});
const PLAIN_HTTP_LAN = { Origin: "http://192.168.1.10:3000", "X-Forwarded-Proto": "http" };
const PLAIN_HTTP_REGISTER_URL = "http://192.168.1.10:3000/api/control-plane/auth/register-owner";

function registerRequest(
  headers: Record<string, string> = {},
  url = "http://127.0.0.1:3000/api/control-plane/auth/register-owner",
  body = VALID_REGISTER_BODY,
): NextRequest {
  return new NextRequest(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
  });
}

describe("POST /api/control-plane/auth/register-owner", () => {
  beforeEach(() => {
    upstreamFetch.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("fails before contacting the control plane when the session secret is a placeholder", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "replace-with-a-random-web-session-secret");
    const { POST } = await import("./route");

    const response = await POST(registerRequest());

    expect(response.status).toBeGreaterThanOrEqual(400);
    // Owner creation consumes the setup code and issues one-time recovery codes,
    // so it must never happen when the session cookie cannot be sealed.
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("refuses plain HTTP from a LAN address before the setup code is spent (J-14)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ session_token: "session-token", recovery_codes: ["code-1"] }), { status: 201 }),
    );
    const { POST } = await import("./route");

    const response = await POST(registerRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_REGISTER_URL));
    const body = (await response.json()) as { error?: { code?: string } };

    // Registering would consume the setup code and show one-time recovery
    // codes for a session the browser then throws away.
    expect(response.status).toBe(403);
    expect(body.error?.code).toBe("INSECURE_TRANSPORT");
    expect(upstreamFetch).not.toHaveBeenCalled();
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("refuses plain HTTP from the transport alone, before the body or the session secret is read", async () => {
    // The refusal is the one specific auth error the screens show, which is
    // safe only because no credential decides it (apps/web/CLAUDE.md).
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    const { POST } = await import("./route");

    const refusals: string[] = [];
    for (const body of [VALID_REGISTER_BODY, "{}", "email=owner%40example.com&bootstrap_code=CODE"]) {
      const request = registerRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_REGISTER_URL, body);
      const response = await POST(request);

      expect(response.status, body).toBe(403);
      expect(response.headers.get("cache-control"), body).toBe("no-store");
      expect(request.bodyUsed, body).toBe(false);
      refusals.push(await response.text());
    }
    // A placeholder secret fails setup over HTTPS; over plain HTTP the
    // transport has already decided.
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "replace-with-a-random-web-session-secret");
    refusals.push(await (await POST(registerRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_REGISTER_URL))).text());

    expect(new Set(refusals)).toEqual(new Set([refusals[0]]));
    expect((JSON.parse(refusals[0]) as { error: { code: string } }).error.code).toBe("INSECURE_TRANSPORT");
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("registers the owner and sets the session cookie when the secret is configured", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ session_token: "session-token", recovery_codes: ["code-1"] }), { status: 201 }),
    );
    const { POST } = await import("./route");

    const response = await POST(registerRequest());

    expect(response.status).toBe(201);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    // Production marks each cookie Secure on its own.
    expect(response.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.value).toBeTruthy();
    expect(response.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.secure).toBe(true);
    expect(response.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.httpOnly).toBe(true);
    expect(response.cookies.get(OWNER_EXISTS_HINT_COOKIE)?.secure).toBe(true);
    expect(response.cookies.get(PENDING_RECOVERY_COOKIE)?.secure).toBe(true);
  });

  function forwardedForSentUpstream(): string | null {
    const init = upstreamFetch.mock.calls[0]?.[1] as RequestInit | undefined;
    return new Headers(init?.headers).get("X-Forwarded-For");
  }

  it.each(["127.0.0.1", "::1", "::ffff:127.0.0.1"])(
    "adds no proxy hop for a browser on loopback (%s), which keeps the dev-only loopback trust working",
    async (loopback) => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
      upstreamFetch.mockResolvedValue(
        new Response(JSON.stringify({ session_token: "session-token", recovery_codes: ["code-1"] }), { status: 201 }),
      );
      const { POST } = await import("./route");

      await POST(registerRequest({ "X-Forwarded-For": loopback }));

      expect(forwardedForSentUpstream()).toBeNull();
    },
  );

  it("forwards a remote browser's address so setup attempts are rate limited per client", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ session_token: "session-token", recovery_codes: ["code-1"] }), { status: 201 }),
    );
    const { POST } = await import("./route");

    await POST(registerRequest({ "X-Forwarded-For": "198.51.100.7" }));

    expect(forwardedForSentUpstream()).toBe("198.51.100.7");
  });
});
