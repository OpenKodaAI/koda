import { afterEach, describe, expect, it, vi } from "vitest";
import { config, proxy } from "./proxy";

describe("web proxy auth gate", () => {
  afterEach(() => {
    delete process.env.CONTROL_PLANE_AUTH_MODE;
    vi.unstubAllEnvs();
    vi.stubEnv("NODE_ENV", "test");
  });

  it("fails closed when the operator session cookie is missing", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      cookies: {
        get: () => undefined,
      },
    } as never);

    expect(response.status).toBe(401);
  });

  it("allows proxy routes when an operator session cookie exists", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      method: "GET",
      cookies: {
        get: () => ({ value: "sealed-session" }),
      },
      headers: {
        get: () => null,
      },
    } as never);

    expect(response.status).toBe(200);
  });

  it("allows public auth bootstrap routes without an operator session cookie", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/auth/bootstrap/exchange"),
      method: "POST",
      cookies: {
        get: () => undefined,
      },
      headers: {
        get: (name: string) => {
          if (name.toLowerCase() === "origin") {
            return "http://localhost";
          }
          return null;
        },
      },
    } as never);

    expect(response.status).toBe(200);
  });

  it("allows development auth bypass only in development mode", () => {
    vi.stubEnv("NODE_ENV", "development");
    process.env.CONTROL_PLANE_AUTH_MODE = "development";

    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      method: "GET",
      cookies: {
        get: () => undefined,
      },
      headers: {
        get: () => null,
      },
    } as never);

    expect(response.status).toBe(200);
  });

  it("blocks cross-site mutations even when a session cookie exists", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      method: "POST",
      cookies: {
        get: () => ({ value: "sealed-session" }),
      },
      headers: {
        get: (name: string) => {
          if (name.toLowerCase() === "origin") {
            return "https://evil.example";
          }
          return null;
        },
      },
    } as never);

    expect(response.status).toBe(403);
  });

  it("keeps the proxy matcher locked to the protected API surfaces", () => {
    expect(config.matcher).toEqual([
      "/api/control-plane/:path*",
      "/api/runtime/:path*",
      "/api/channels/:path*",
    ]);
  });
});
