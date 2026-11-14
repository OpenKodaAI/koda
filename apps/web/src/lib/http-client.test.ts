import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";
import { requestJson } from "@/lib/http-client";

describe("requestJson", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function rejection(): Promise<ApiError> {
    const error = await requestJson("/api/control-plane/auth/login", { method: "POST" }).catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }

  it("carries the error code a route attached, so a screen can branch on it", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "INSECURE_TRANSPORT",
            message: "Sign-in needs HTTPS.",
            user_action: "Use a reverse proxy.",
          },
        }),
        { status: 403 },
      ),
    );

    const error = await rejection();

    expect(error.status).toBe(403);
    expect(error.reason).toBe("INSECURE_TRANSPORT");
    expect(error.message).toBe("Sign-in needs HTTPS. Use a reverse proxy.");
    expect(error.retryAfterSeconds).toBeNull();
  });

  it("keeps a rejected sign-in (401) on the form instead of forcing a sign-out", async () => {
    // The control plane answers bad credentials with 401 (D-135); only a 401 from a
    // session-guarded route means the session ended.
    const forcedSignOuts: Event[] = [];
    const listener = (event: Event) => forcedSignOuts.push(event);
    window.addEventListener("koda:force-sign-out", listener);
    try {
      fetchMock.mockImplementation(
        async () => new Response(JSON.stringify({ error: "Invalid credentials." }), { status: 401 }),
      );

      const error = await rejection();

      expect(error.status).toBe(401);
      expect(error.message).toBe("Invalid credentials.");
      expect(forcedSignOuts).toHaveLength(0);

      await requestJson("/api/control-plane/agents").catch(() => undefined);
      expect(forcedSignOuts).toHaveLength(1);
    } finally {
      window.removeEventListener("koda:force-sign-out", listener);
    }
  });

  it("keeps the wait a throttled response asks for", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "Too many attempts. Try again later." }), {
        status: 429,
        headers: { "Retry-After": "60" },
      }),
    );

    const error = await rejection();

    expect(error.status).toBe(429);
    expect(error.retryAfterSeconds).toBe(60);
    expect(error.reason).toBeUndefined();
  });

  it("reports no wait and no reason when the response names neither", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "Invalid credentials." }), { status: 400 }),
    );

    const error = await rejection();

    expect(error.status).toBe(400);
    expect(error.message).toBe("Invalid credentials.");
    expect(error.retryAfterSeconds).toBeNull();
    expect(error.reason).toBeUndefined();
  });

  it("keeps both the code and the wait when a response carries both", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "RATE_LIMITED", message: "Slow down." } }), {
        status: 429,
        headers: { "Retry-After": "7" },
      }),
    );

    const error = await rejection();

    expect(error.reason).toBe("RATE_LIMITED");
    expect(error.retryAfterSeconds).toBe(7);
    expect(error.message).toBe("Slow down.");
  });
});
