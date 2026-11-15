import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import type { NextResponse } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WEB_OPERATOR_SESSION_COOKIE } from "@/lib/web-operator-session-constants";
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

  it("lets the pre-login onboarding status probe through without a session cookie", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/onboarding/status"),
      method: "GET",
      cookies: { get: () => undefined },
      headers: { get: () => null },
    } as never);

    expect(response.status).toBe(200);
  });

  it("keeps onboarding readiness behind the operator session cookie", () => {
    const response = proxy({
      nextUrl: new URL("http://localhost/api/control-plane/onboarding/readiness"),
      method: "GET",
      cookies: { get: () => undefined },
      headers: { get: () => null },
    } as never);

    expect(response.status).toBe(401);
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

  function pageRequest(url: string, headers: Record<string, string>, cookies: Record<string, string> = {}) {
    const nextUrl = new URL(url);
    return {
      nextUrl: Object.assign(nextUrl, {
        clone: () => new URL(nextUrl.toString()),
      }),
      method: "GET",
      cookies: {
        get: (name: string) => (name in cookies ? { value: cookies[name] } : undefined),
      },
      headers: new Headers(headers),
    } as never;
  }

  it.each([
    ["production", true],
    ["development", false],
  ] as const)("in %s clears a malformed session cookie with Secure=%s", (nodeEnv, secure) => {
    vi.stubEnv("NODE_ENV", nodeEnv);
    vi.stubEnv("SECURE_COOKIES", "");
    vi.stubEnv("ALLOW_INSECURE_COOKIES", "");
    const https = { host: "koda.example.com", "x-forwarded-proto": "https" };

    const response = proxy(
      pageRequest("http://koda.example.com/executions", https, {
        [WEB_OPERATOR_SESSION_COOKIE]: "not-a-sealed-token",
      }),
    ) as NextResponse;

    const cleared = response.cookies.get(WEB_OPERATOR_SESSION_COOKIE);
    expect(cleared?.value).toBe("");
    expect(cleared?.maxAge).toBe(0);
    expect(cleared?.secure).toBe(secure);
  });

  it("sends a page over plain HTTP from a LAN address to /login once, and /login then renders (J-14)", () => {
    vi.stubEnv("NODE_ENV", "production");
    const lan = { host: "192.168.1.10:3000", "x-forwarded-proto": "http" };
    // The owner hint cookie is Secure, so over this transport it never comes
    // back and cannot choose between /setup and /login.
    const first = proxy(pageRequest("http://192.168.1.10:3000/executions", lan));
    expect(first.status).toBe(307);
    expect(first.headers.get("location")).toBe(
      "http://192.168.1.10:3000/login?next=%2Fexecutions",
    );

    // No second hop: /login renders and explains, so there is no loop.
    const second = proxy(pageRequest("http://192.168.1.10:3000/login?next=%2Fexecutions", lan));
    expect(second.status).toBe(200);
    expect(second.headers.get("location")).toBeNull();

    // /setup and /forgot-password render their own explanation too.
    for (const page of ["/setup", "/forgot-password"]) {
      const direct = proxy(pageRequest(`http://192.168.1.10:3000${page}`, lan));
      expect(direct.status).toBe(200);
      expect(direct.headers.get("location")).toBeNull();
    }

    // Loopback keeps the first-run redirect: browsers keep Secure cookies there.
    const loopback = proxy(
      pageRequest("http://127.0.0.1:3000/", { host: "127.0.0.1:3000", "x-forwarded-proto": "http" }),
    );
    expect(loopback.headers.get("location")).toBe("http://127.0.0.1:3000/setup?next=%2F");
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

  it("tells a throttled client to retry when its window takes the next request", () => {
    // The auth screens read this Retry-After to say how long to wait (ADR-038).
    const start = Date.now();
    vi.useFakeTimers({ now: start, toFake: ["Date"] });
    const apiRequest = () =>
      proxy({
        nextUrl: new URL("http://localhost/api/control-plane/auth/status"),
        method: "GET",
        cookies: { get: () => undefined },
        headers: {
          get: (name: string) => (name.toLowerCase() === "x-forwarded-for" ? "198.51.100.77" : null),
        },
      } as never);

    try {
      const burst = Array.from({ length: 120 }, () => apiRequest().status);
      const refused = apiRequest();
      vi.setSystemTime(start + 59_999);
      const early = apiRequest().status;
      vi.setSystemTime(start + 60_000);
      const onTime = apiRequest().status;

      expect(new Set(burst)).toEqual(new Set([200]));
      expect(refused.status).toBe(429);
      expect(refused.headers.get("Retry-After")).toBe("60");
      expect(refused.headers.get("Cache-Control")).toBe("no-store");
      expect(early).toBe(429);
      expect(onTime).toBe(200);
    } finally {
      vi.useRealTimers();
    }
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
      "/((?!_next/static|_next/image|_next/hmr|favicon.ico|apple-icon.png|robots.txt|sitemap.xml).*)",
    ]);
  });

  it("excludes the dev HMR path the installed Next.js serves", async () => {
    // router-server.js matches HMR upgrades on `${hmrPrefix}/_next/<path>`
    // (`_next/webpack-hmr` up to 16.2, `_next/hmr` from 16.4).
    const routerServer = await readFile(createRequire(import.meta.url).resolve("next/dist/server/lib/router-server.js"), "utf8");
    const hmrPath = routerServer.match(/`\$\{hmrPrefix\}\/(_next\/[\w-]+)`/)?.[1];

    expect(hmrPath).toBeDefined();
    expect(config.matcher[0]).toContain(`|${hmrPath}|`);
  });
});
