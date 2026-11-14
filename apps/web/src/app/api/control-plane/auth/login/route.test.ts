import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  OWNER_EXISTS_HINT_COOKIE,
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

const VALID_LOGIN_BODY = JSON.stringify({ identifier: "owner@example.com", password: "a-strong-password-123" });
const PLAIN_HTTP_LAN = { Origin: "http://192.168.1.10:3000", "X-Forwarded-Proto": "http" };
const PLAIN_HTTP_LOGIN_URL = "http://192.168.1.10:3000/api/control-plane/auth/login";

function loginRequest(
  headers: Record<string, string> = {},
  url = "http://127.0.0.1:3000/api/control-plane/auth/login",
  body = VALID_LOGIN_BODY,
): NextRequest {
  return new NextRequest(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
  });
}

function upstreamHeaders(): Headers {
  const init = upstreamFetch.mock.calls[0]?.[1] as RequestInit | undefined;
  return new Headers(init?.headers);
}

describe("POST /api/control-plane/auth/login", () => {
  beforeEach(() => {
    upstreamFetch.mockReset();
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("fails before contacting the control plane and keeps the reason server-side", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "replace-with-a-random-web-session-secret");
    const { POST } = await import("./route");

    const response = await POST(loginRequest());
    const body = (await response.json()) as { error?: string };

    expect(response.status).toBeGreaterThanOrEqual(500);
    expect(upstreamFetch).not.toHaveBeenCalled();
    expect(body.error).toBe("Unable to sign in.");
    expect(JSON.stringify(body)).not.toContain("WEB_OPERATOR_SESSION_SECRET");
  });

  it("refuses plain HTTP from a LAN address before contacting the control plane (J-14)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ session_token: "session-token" }), { status: 200 }),
    );
    const { POST } = await import("./route");

    const response = await POST(loginRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_LOGIN_URL));
    const body = (await response.json()) as { error?: { code?: string; message?: string } };

    // The browser would drop the Secure session cookie, so signing in here
    // would only start a session nobody can use.
    expect(response.status).toBe(403);
    expect(body.error?.code).toBe("INSECURE_TRANSPORT");
    expect(body.error?.message).toContain("http://192.168.1.10:3000");
    expect(upstreamFetch).not.toHaveBeenCalled();
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("no-store");

    // The same sign-in through a proxy that terminated HTTPS goes through.
    const viaHttps = await POST(
      loginRequest(
        { Origin: "https://koda.example.com", Host: "koda.example.com", "X-Forwarded-Proto": "https" },
        "http://koda.example.com/api/control-plane/auth/login",
      ),
    );

    expect(viaHttps.status).toBe(200);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    // Each cookie is Secure on its own; one Secure cookie in the joined header
    // would hide a session cookie that lost the flag.
    expect(viaHttps.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.secure).toBe(true);
    expect(viaHttps.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.httpOnly).toBe(true);
    expect(viaHttps.cookies.get(OWNER_EXISTS_HINT_COOKIE)?.secure).toBe(true);
  });

  it("refuses plain HTTP from the transport alone, before the body or the session secret is read", async () => {
    // The refusal is the one specific auth error the screens show, which is
    // safe only because no credential decides it (apps/web/CLAUDE.md).
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    const { POST } = await import("./route");

    const refusals: string[] = [];
    for (const body of [VALID_LOGIN_BODY, "{}", "identifier=owner%40example.com&password=x"]) {
      const request = loginRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_LOGIN_URL, body);
      const response = await POST(request);

      expect(response.status, body).toBe(403);
      expect(response.headers.get("cache-control"), body).toBe("no-store");
      expect(request.bodyUsed, body).toBe(false);
      refusals.push(await response.text());
    }
    // A placeholder secret fails sign-in with a 500 over HTTPS; over plain
    // HTTP the transport has already decided.
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "replace-with-a-random-web-session-secret");
    refusals.push(await (await POST(loginRequest(PLAIN_HTTP_LAN, PLAIN_HTTP_LOGIN_URL))).text());

    expect(new Set(refusals)).toEqual(new Set([refusals[0]]));
    expect((JSON.parse(refusals[0]) as { error: { code: string } }).error.code).toBe("INSECURE_TRANSPORT");
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("signs in through an HTTPS proxy that rewrites Origin to its plain-HTTP upstream", async () => {
    // What a browser on https://koda.example.com sends through a proxy that
    // sets `Origin $scheme://$host` for its upstream. Its Fetch Metadata shows
    // the browser is on a secure URL and will keep the Secure cookies, which
    // is also why the login page showed it the form.
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(
      new Response(JSON.stringify({ session_token: "session-token" }), { status: 200 }),
    );
    const { POST } = await import("./route");

    const response = await POST(
      loginRequest(
        {
          Host: "koda-web:3000",
          Origin: "http://koda-web:3000",
          "X-Forwarded-Proto": "https",
          "Sec-Fetch-Site": "same-origin",
          "Sec-Fetch-Mode": "cors",
        },
        "http://koda-web:3000/api/control-plane/auth/login",
      ),
    );

    expect(response.status).toBe(200);
    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    expect(response.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.secure).toBe(true);
    expect(response.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.httpOnly).toBe(true);
  });

  it("forwards the browser address so the control plane rate limits each client separately", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_OPERATOR_SESSION_SECRET", "0123456789abcdef0123456789abcdef");
    upstreamFetch.mockResolvedValue(new Response(JSON.stringify({ error: "Invalid credentials." }), { status: 400 }));
    const { POST } = await import("./route");

    // A spoofed entry to the left of the address the edge proxy appended is ignored.
    await POST(loginRequest({ "X-Forwarded-For": "10.9.9.9, 198.51.100.7" }));

    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    expect(upstreamHeaders().get("X-Forwarded-For")).toBe("198.51.100.7");
  });
});
