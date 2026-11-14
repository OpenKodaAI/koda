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

function loginRequest(): NextRequest {
  return new NextRequest("http://127.0.0.1:3000/api/control-plane/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier: "owner@example.com", password: "a-strong-password-123" }),
  });
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
});
