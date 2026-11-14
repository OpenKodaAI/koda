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
  });

  it("reports no wait when the response names none", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "Invalid credentials." }), { status: 400 }),
    );

    const error = await rejection();

    expect(error.status).toBe(400);
    expect(error.message).toBe("Invalid credentials.");
    expect(error.retryAfterSeconds).toBeNull();
  });
});
