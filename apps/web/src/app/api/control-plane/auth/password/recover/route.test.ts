import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const upstreamFetch = vi.fn();

vi.mock("@/lib/api-utils", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-utils")>();
  return { ...actual, upstreamFetch };
});

vi.mock("@/lib/request-origin", () => ({
  isTrustedDashboardRequest: () => true,
}));

function recoverRequest(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://127.0.0.1:3000/api/control-plane/auth/password/recover", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({
      identifier: "owner@example.com",
      recovery_code: "ABCD-EFGH-JKLM",
      new_password: "a-strong-password-123",
    }),
  });
}

describe("POST /api/control-plane/auth/password/recover", () => {
  beforeEach(() => {
    upstreamFetch.mockReset();
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
