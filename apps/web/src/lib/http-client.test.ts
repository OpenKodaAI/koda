import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";
import { requestJson } from "@/lib/http-client";

afterEach(() => {
  vi.unstubAllGlobals();
});

function respondWith(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("requestJson errors", () => {
  it("carries the error code a route attached, so a screen can branch on it", async () => {
    respondWith(403, {
      error: {
        code: "INSECURE_TRANSPORT",
        message: "Sign-in needs HTTPS.",
        user_action: "Use a reverse proxy.",
      },
    });

    const error = await requestJson("/api/control-plane/auth/login", { method: "POST" }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(403);
    expect((error as ApiError).reason).toBe("INSECURE_TRANSPORT");
    expect((error as ApiError).message).toBe("Sign-in needs HTTPS. Use a reverse proxy.");

    // A plain error string keeps its message and has no reason.
    respondWith(401, { error: "Invalid credentials." });
    const plain = await requestJson("/api/control-plane/auth/login", { method: "POST" }).catch(
      (caught: unknown) => caught,
    );
    expect((plain as ApiError).message).toBe("Invalid credentials.");
    expect((plain as ApiError).reason).toBeUndefined();
  });
});
