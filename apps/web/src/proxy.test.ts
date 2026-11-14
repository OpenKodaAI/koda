import { afterEach, describe, expect, it, vi } from "vitest";
import { config, proxy } from "./proxy";

describe("web proxy auth gate", () => {
  afterEach(() => {
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

  it("allows public password recovery without an operator session cookie", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/auth/password/recover"),
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

  it("redirects /setup to /login when the owner hint cookie is present", () => {
    const nextUrl = new URL("http://localhost/setup?next=%2Fexecutions");
    const response = proxy({
      nextUrl: Object.assign(nextUrl, {
        clone: () => new URL(nextUrl.toString()),
      }),
      method: "GET",
      cookies: {
        get: (name: string) =>
          name === "koda_has_owner" ? { value: "1" } : undefined,
      },
      headers: {
        get: () => null,
      },
    } as never);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost/login?next=%2Fexecutions",
    );
  });

  it("requires the operator session cookie even in development mode", () => {
    vi.stubEnv("NODE_ENV", "development");

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

    expect(response.status).toBe(401);
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

  it("rate limits each client address separately instead of one shared bucket", () => {
    const apiRequest = (forwardedFor: string) =>
      proxy({
        nextUrl: new URL("http://localhost/api/control-plane/auth/status"),
        method: "GET",
        cookies: { get: () => undefined },
        headers: {
          get: (name: string) => (name.toLowerCase() === "x-forwarded-for" ? forwardedFor : null),
        },
      } as never);

    const flooding = Array.from({ length: 130 }, () => apiRequest("10.9.9.9, 198.51.100.66").status);
    expect(flooding).toContain(429);
    // The flood above spends only its own window; another browser is unaffected.
    expect(apiRequest("192.0.2.10").status).toBe(200);
  });

  it("charges every address of an IPv6 /64 to one window", () => {
    const apiRequest = (forwardedFor: string) =>
      proxy({
        nextUrl: new URL("http://localhost/api/control-plane/auth/status"),
        method: "GET",
        cookies: { get: () => undefined },
        headers: {
          get: (name: string) => (name.toLowerCase() === "x-forwarded-for" ? forwardedFor : null),
        },
      } as never);

    // A client rotating through its own /64 gets no fresh window per address.
    const rotating = Array.from({ length: 130 }, (_, n) => apiRequest(`2001:db8:5:6::${n.toString(16)}`).status);
    expect(rotating).toContain(429);
    expect(apiRequest("2001:db8:5:7::1").status).toBe(200);
  });

  it.each([
    ["login-session", "/api/control-plane/providers/x/connection/login/abc", 20, 401],
    ["general", "/api/control-plane/auth/status", 120, 200],
  ])("bounds the clients the %s window tracks", (_name, path, limit, allowedStatus) => {
    const apiRequest = (forwardedFor: string) =>
      proxy({
        nextUrl: new URL(`http://localhost${path}`),
        method: "GET",
        cookies: { get: () => undefined },
        headers: {
          get: (name: string) => (name.toLowerCase() === "x-forwarded-for" ? forwardedFor : null),
        },
      } as never);

    const exhausted = Array.from({ length: limit + 1 }, () => apiRequest("198.51.100.200").status);
    expect(exhausted.at(-1)).toBe(429);
    // Unauthenticated requests from 4096 distinct /64s, as from one routed /48.
    for (let n = 0; n < 4096; n += 1) {
      const address = `2001:db8:${(0x1000 + (n >> 8)).toString(16)}:${(n & 0xff).toString(16)}::1`;
      expect(apiRequest(address).status).toBe(allowedStatus);
    }
    // The window keeps the 4096 most recent clients, so the oldest is gone.
    expect(apiRequest("198.51.100.200").status).toBe(allowedStatus);
  });

  it("keeps the proxy matcher locked to the protected API surfaces", () => {
    expect(config.matcher).toEqual([
      "/((?!_next/static|_next/image|_next/webpack-hmr|favicon.ico|apple-icon.png|robots.txt|sitemap.xml).*)",
    ]);
  });
});
