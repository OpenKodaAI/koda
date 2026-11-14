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

function registerRequest(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://127.0.0.1:3000/api/control-plane/auth/register-owner", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ email: "owner@example.com", password: "a-strong-password-123", bootstrap_code: "CODE" }),
  });
}

describe("POST /api/control-plane/auth/register-owner", () => {
  beforeEach(() => {
    upstreamFetch.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
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
    expect(response.headers.get("set-cookie")).toBeTruthy();
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
