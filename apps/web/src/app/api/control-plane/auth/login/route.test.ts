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

function loginRequest(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://127.0.0.1:3000/api/control-plane/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ identifier: "owner@example.com", password: "a-strong-password-123" }),
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
